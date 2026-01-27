"""
Creates the YAGO facts from the Wikidata facts

CC-BY 2022-2025 Fabian M. Suchanek

Call:
  python3 make-facts.py

Input:
- 01-yago-final-schema.ttl
- 02-yago-taxonomy-to-rename.tsv
- Wikidata file

Output:
- 03-yago-facts-to-type-check.tsv

Algorithm:
- run through all entities of Wikidata, with its associated facts
  - translate Wikidata classes/properties to YAGO classes/properties
  - check for disjointness of classes
  - check cardinality constraints
  - check domain constraint
  - check range constraints
  - write out facts that fulfill the constraints to yago-facts-to-type-check.tsv  
"""

##########################################################################
#             Booting
##########################################################################

import Prefixes
import glob
import TsvUtils
import TurtleUtils
from TurtleUtils import Graph
import sys
import re
import os
from urllib import parse
import Evaluator
from Schema import YagoSchema
from collections import defaultdict
from typing import Optional, Dict, Set, Tuple, Any, Iterator, List

TEST=len(sys.argv)>1 and sys.argv[1]=="--test"
FOLDER="test-data/03-make-facts/" if TEST else "yago-data/"
WIKIDATA_FILE= "test-data/03-make-facts/00-wikidata.ttl" if TEST else "../wikidata.ttl"

##########################################################################
#             Debugging
##########################################################################

def debug(*message: Any) -> None:
    """ Prints a message if we're in TEST mode"""
    if TEST:
        sys.stdout.buffer.write(b"  DEBUG: ")
        for m in message:
            # Using this instead of print to allow printing unicode chars to pipes
            sys.stdout.buffer.write(str(m).encode('utf8'))
            sys.stdout.buffer.write(b" ")
        print("")
    
def getFirst(iterable: Iterator[Any]) -> Optional[Any]:
    """ Returns the first element of an iterable or None"""
    try:
        return next(iter(iterable))
    except StopIteration:
        return None
    
##########################################################################
#             Cleaning of entities
##########################################################################

def translatePropertiesAndClasses(entityFacts: Graph, yagoSchema: YagoSchema) -> Tuple[Graph, Dict[Tuple[str, str, str], Tuple[Optional[str], Optional[str]]]]:
    """ Replaces properties by their YAGO properties, and classes by their YAGO equivalents, returns new graph and fact dates """
    newGraph: Graph = Graph()
    dates: Dict[Tuple[str, str, str], Tuple[Optional[str], Optional[str]]] = {}
    for (subject, predicate, obj) in entityFacts:
        startDate, endDate = getStartAndEndDate(subject, predicate, obj, entityFacts)
        subject = yagoSchema.wikidataProperties[subject].identifier if subject in yagoSchema.wikidataProperties else subject
        predicate = yagoSchema.wikidataProperties[predicate].identifier if predicate in yagoSchema.wikidataProperties else predicate
        obj = yagoSchema.wikidataProperties[obj].identifier if obj in yagoSchema.wikidataProperties else obj
        subject = yagoSchema.wikidataClasses[subject].identifier if subject in yagoSchema.wikidataClasses else subject
        predicate = yagoSchema.wikidataClasses[predicate].identifier if predicate in yagoSchema.wikidataClasses else predicate
        obj = yagoSchema.wikidataClasses[obj].identifier if obj in yagoSchema.wikidataClasses else obj
        newGraph.add((subject, predicate, obj))
        if startDate or endDate:
            dates[(subject, predicate, obj)] = (startDate, endDate)
    return (newGraph, dates)
   
def handleWebPages(entityFacts: Graph) -> None:
    """ Changes <page, schema:about, entity> to <entity, mainEntityOfPage, page> """
    for page, predicate, entity in entityFacts.triplesWithPredicate(Prefixes.schemaAbout):
        entityFacts.remove((page, Prefixes.schemaAbout, entity))
        entityFacts.add((entity, Prefixes.schemaPage, page))
        debug("Fixed", entity, Prefixes.schemaPage, page)
    
def handleTypeAssertions(entityFacts: Graph, yagoTaxonomyUp: Dict[str, Set[str]]) -> None:
    """Replace all facts <subject, wikidata:type, class> by <subject, rdf:type, class>"""
    # Given types are mostly meta stuff
    mainEntity: str = entityFacts.mainSubject()
    entityFacts.removeObjects(mainEntity, Prefixes.rdfType)
    # If you're a class, say it
    if mainEntity in yagoTaxonomyUp:
        entityFacts.add((mainEntity, Prefixes.rdfType, Prefixes.rdfsClass))
    else:
        for predicate in list(entityFacts.predicatesOf(mainEntity)):
            if predicate == Prefixes.wikidataType or predicate == Prefixes.wikidataOccupation:
                for obj in entityFacts.objectsOf(mainEntity, predicate):
                    entityFacts.add((mainEntity, Prefixes.rdfType, obj))  
            # Anything that has a parent taxon is an instance of taxon
            if predicate == "schema:parentTaxon":
                entityFacts.add((mainEntity, Prefixes.rdfType, Prefixes.schemaTaxon))
    entityFacts.removeObjects(mainEntity, Prefixes.wikidataType)
    entityFacts.removeObjects(mainEntity, Prefixes.wikidataOccupation)
        
##########################################################################
#             Start and end dates
##########################################################################

# Start and end dates are encoded as follows in Wikidata:
#
# # Belgium has 11m inhabitants
# wd:Q31 wdt:P1082 "+11431406"^^xsd:decimal .
# 
# # This is true in the year 2014
# 
# wd:Q31 p:P1082 wds:Q31-93ba9638-404b-66ac-2733-e6292666a326 .
# wds:Q31-93ba9638-404b-66ac-2733-e6292666a326 a wikibase:Statement ;
#	ps:P1082 "+11150516"^^xsd:decimal ;
#	pq:P585 "2014-01-01T00:00:00Z"^^xsd:dateTime ;
    
def getStartAndEndDate(subject: str, predicate: str, obj: str, entityGraph: Graph) -> Tuple[Optional[str], Optional[str]]:
    """ Returns a tuple of a start date and an end date for this fact.
        Unknown components are None. """
    # The property should be in the namespace WDT
    if not predicate.startswith("wdt:"):
        return (None, None)
    # Translate to the namespace P
    pStatement: str = "p:" + predicate[4:]
    # Translate to the namespace PS
    pValue: str = "ps:" + predicate[4:]
    # Find all meta statements about (subject, predicate, _)
    for statement in entityGraph.objectsOf(subject, pStatement):
        # If the meta-statement concerns indeed the object obj...
        if (statement, pValue, obj) in entityGraph:
            # If there is a "duringTime" (pq:P585), return that one
            for duringTime in entityGraph.objectsOf(statement, Prefixes.wikidataDuring):
                if TurtleUtils.isDate(duringTime):
                    return (duringTime, duringTime)
                else:
                    debug("Removing bad date", duringTime)
            # Otherwise extract start time and end time
            startDate: Optional[str] = getFirst(entityGraph.objectsOf(statement, Prefixes.wikidataStart))
            endDate: Optional[str] = getFirst(entityGraph.objectsOf(statement, Prefixes.wikidataEnd))
            start: Optional[str] = normalizeDate(startDate) if startDate and TurtleUtils.isDate(startDate) else None
            end: Optional[str] = normalizeDate(endDate) if endDate and TurtleUtils.isDate(endDate) else None
            return (start, end)
    return (None, None)

##########################################################################
#             Taxonomy checks
##########################################################################

def handleAndReturnTypes(entityFacts: Graph, yagoSchema: YagoSchema, yagoTaxonomyUp: Dict[str, Set[str]]) -> Set[str]:
    """Removes disjoint classes and shortcuts, returns types"""
    mainEntity: str = entityFacts.mainSubject()
    superTypes: Set[str] = set()
    # Sort the list to make this deterministic
    directTypes: List[str] = sorted(entityFacts.objectsOf(mainEntity, Prefixes.rdfType))
    directTypesSet: Set[str] = set(directTypes)
    for type_ in directTypes:
        superClasses: Set[str] = getSuperClasses(type_, yagoTaxonomyUp, set())
        for superClass in superClasses:
            if superClass in yagoSchema.classes:
                for disjointYagoClass in yagoSchema.classes[superClass].disjointWith:
                    disjointId = disjointYagoClass.identifier
                    if disjointId in superTypes or disjointId in directTypesSet: 
                        entityFacts.remove((mainEntity, Prefixes.rdfType, type_))
                        debug("Removed disjoint type", type_, "from", mainEntity, "since disjoint with", disjointYagoClass)
                        break
        else:
            superClasses.remove(type_)
            superTypes.update(superClasses)
            
    # Remove shortcuts        
    for type_ in directTypes:
        if type_ in superTypes:
            entityFacts.remove((mainEntity, Prefixes.rdfType, type_))
            debug("Removed shortcut type", type_, "from", mainEntity, superTypes)
    superTypes.update(directTypes)
    return superTypes    
    
def getSuperClasses(class_: str, yagoTaxonomyUp: Dict[str, Set[str]], classes: Set[str]) -> Set[str]:
    """Adds all superclasses of a class <class_> (including <class_>) to the set <classes>, returns it; start with empty classes set"""
    classes.add(class_)
    # Make a check before because it's a defaultdict,
    # which would create class_ if it's not there
    if class_ in yagoTaxonomyUp:
        for superClass in yagoTaxonomyUp[class_]:
            getSuperClasses(superClass, yagoTaxonomyUp, classes)
    return classes
        
##########################################################################
#             Handling domains and range
##########################################################################

def handleDomain(entityFacts: Graph, yagoSchema: YagoSchema, fullTransitiveClasses: Set[str]) -> None:
    """ Performs a domain check, removes offending facts"""
    mainEntity: str = entityFacts.mainSubject()
    for predicate in list(entityFacts.predicatesOf(mainEntity)):
        if predicate == Prefixes.rdfType:
            continue
        yagoProperty = yagoSchema.properties.get(predicate, None)
        if not yagoProperty:
           entityFacts.removeObjects(mainEntity, predicate)
           debug("Removed unknown predicate", mainEntity, predicate)
           continue
        # Use set intersection for efficient membership check
        subjectTypesSet: Set[str] = set(yagoProperty.subjectTypes)
        if not (fullTransitiveClasses & subjectTypesSet):
            # Remove all objects for this predicate if domain check fails
            debug("Domain check failed for", mainEntity, yagoProperty, fullTransitiveClasses)
            for obj in list(entityFacts.objectsOf(mainEntity, predicate)):
                entityFacts.remove((mainEntity, predicate, obj))
                     
def isURI(s: str) -> bool: 
    """TRUE if s conforms to xsd:anyUri, as explained here:
    https://stackoverflow.com/questions/14466585/is-this-regex-correct-for-xsdanyuri """
    return not re.search("(%(?![0-9A-F]{2})|#.*#)", s)

def normalizeString(s: Optional[str]) -> Optional[str]:
    """ Makes sure that a string does not contain invalid characters or languages"""
    if not s or not s.startswith('"'):
        return s
    return s.replace("\uFFFD", "_").replace('"@zh-classical', '"@zh')

def normalizeDate(literal: Optional[str]) -> Optional[str]:
    """ Converts midnight dates to dates"""
    return re.sub('T00:00:00Z"\\^\\^xsd:dateTime$', '"^^xsd:date', literal) if literal else None
    
def cleanLiteralObject(obj: str, datatype: str) -> Optional[str]:
    """ Returns a version of obj that corresponds to the datatype -- or None"""
    if datatype == Prefixes.xsdAnytype:
        return obj if obj.startswith('"') else None
    if datatype == Prefixes.xsdAnyURI and obj.startswith('<'):
        obj = obj[1:-1]
        if not isURI(obj):
            return None
        return '"' + obj + '"^^xsd:anyURI'
    if datatype == Prefixes.xsdString and obj.startswith('<'):
        return '"' + obj[1:-1] + '"'       
    literalValue, _, lang, literalDataType = TurtleUtils.splitLiteral(obj)
    if literalValue is None:
        return None
    if datatype == Prefixes.xsdAnyURI:
        return '"' + literalValue + '"^^' + Prefixes.xsdAnyURI if isURI(literalValue) else None
    if datatype == Prefixes.xsdString:
        return '"' + literalValue + '"'
    if datatype == Prefixes.rdfLangString:
        return obj if literalDataType is None and lang is not None else None
    if datatype == Prefixes.xsdDateTime:
        # Erroneous default dates in Wikidata
        if obj.startswith(Prefixes.INVALID_DATE_PREFIX):
           return None
        # Strings that are longer than any possible date   
        if len(obj) > Prefixes.MAX_DATE_LENGTH:
           return None
        # Fall through
    return obj if literalDataType == datatype else None
        
def cleanObject(obj: str, yagoProperty: Any) -> Optional[str]:
    """Returns an object that conforms to the range of the yagoProperty -- or None in case of failure.
    Returns normalized object (normalized string and date) ready for use."""
    # Patterns are verified in a fall-through fashion,
    # because verifying a pattern is a necessary but not sufficient condition
    if yagoProperty.pattern:
       objectValue = TurtleUtils.splitLiteral(obj)[0]
       if objectValue is None:
           debug("Object is not a literal", obj)
           return None
       if not re.match(yagoProperty.pattern, objectValue):
            debug("Object does not match regex:", objectValue, yagoProperty.pattern)
            return None
    
    # TRUE if this type admits entity objects (as opposed to literals)
    couldBeEntity: bool = False
    
    for objectType in yagoProperty.objectTypes:
        if objectType.startswith("xsd:") or objectType.startswith("rdf:") or objectType.startswith("geo:"):
            cleanedObj = cleanLiteralObject(obj, objectType)
            if cleanedObj:
                # Normalize string and date - this is the only place normalization happens
                return normalizeDate(normalizeString(cleanedObj))
        else:
            couldBeEntity = True
            
    # If the object is a literal, there is no chance we can make it fit the range
    if TurtleUtils.isLiteral(obj):
        debug("Could not match any object type for", obj, yagoProperty.objectTypes)
        return None
    
    # If the object is not a literal, it can still work if we allow entities
    return obj if couldBeEntity else None

def handleRange(entityFacts: Graph, yagoSchema: YagoSchema) -> None:
    """ Performs a range check, removes offending facts"""
    mainEntity: str = entityFacts.mainSubject()
    for predicate in list(entityFacts.predicatesOf(mainEntity)):
        yagoProperty = yagoSchema.properties.get(predicate, None)
        if not yagoProperty:
           continue 
        for obj in list(entityFacts.objectsOf(mainEntity, predicate)):
            # cleanObject already returns normalized object, no need to normalize again
            cleanObj = cleanObject(obj, yagoProperty)
            if cleanObj is None:
                entityFacts.remove((mainEntity, predicate, obj))
                debug("Range check failed for", obj, yagoProperty, yagoProperty.objectTypes)
            elif cleanObj != obj:
                debug("Cleaned object", obj, cleanObj)
                entityFacts.remove((mainEntity, predicate, obj))         
                entityFacts.add((mainEntity, predicate, cleanObj))
                

##########################################################################
#             Handling min and max counts
##########################################################################

def isSecondaryWikidataClass(entityFacts: Graph, yagoSchema: YagoSchema) -> bool:
    """ TRUE if entityFacts describe a class that is mapped to a YAGO class, and this class is not the first among them"""
    mainEntity: str = entityFacts.mainSubject()
    if mainEntity in yagoSchema.wikidataClasses:
        candidates: List[str] = list(yagoSchema.wikidataClasses[mainEntity].fromClasses)
        candidates.sort()
        debug("Is Wikidata class", mainEntity, candidates)
        return mainEntity != candidates[0]
    return False

def handleMaxCounts(entityFacts: Graph, yagoSchema: YagoSchema, isSecondaryClass: bool = False) -> None:
    """ Performs uniqueLang and maxCount checks, removes offending facts """
    mainEntity: str = entityFacts.mainSubject()            
    for predicate in list(entityFacts.predicatesOf(mainEntity)):        
        yagoProperty = yagoSchema.properties.get(predicate, None)
        if not yagoProperty:
            continue
        # For secondary classes, we do not add anything that might violate maxcounts
        if isSecondaryClass and (yagoProperty.maxCount or yagoProperty.uniqueLang):
            debug("Secondary class", mainEntity, "loses", predicate)
            entityFacts.removeObjects(mainEntity, predicate)
            continue
        # Check maxcount    
        if yagoProperty.maxCount and len(entityFacts.objectsOf(mainEntity, predicate)) > yagoProperty.maxCount:
            objects: List[str] = list(entityFacts.objectsOf(mainEntity, predicate))
            objects.sort()
            for i in range(yagoProperty.maxCount, len(objects)):
                entityFacts.remove((mainEntity, predicate, objects[i]))
        # Check unique languages
        if yagoProperty.uniqueLang:
            languages: Set[str] = set()
            objects = list(entityFacts.objectsOf(mainEntity, predicate))
            objects.sort(key=len)
            objects.reverse()
            debug("Unique language for", mainEntity, yagoProperty, objects)
            if not objects:
                debug("No objects:", mainEntity, predicate, objects)
                continue
            for obj in objects:
                _, _, lang, _ = TurtleUtils.splitLiteral(obj)
                if lang:
                   if lang in languages:
                        debug("Duplicate language:", mainEntity, predicate, lang)
                        entityFacts.remove((mainEntity, predicate, obj))
                   else:
                        languages.add(lang)

def checkMinCounts(entityFacts: Graph, yagoSchema: YagoSchema, isSecondaryClass: bool) -> bool:
    """ TRUE if the object passes the MinCount checks"""
    mainEntity: str = entityFacts.mainSubject()            
    for predicate in entityFacts.predicatesOf(mainEntity):        
        yagoProperty = yagoSchema.properties.get(predicate, None)
        if yagoProperty and yagoProperty.minCount and len(entityFacts.objectsOf(mainEntity, predicate)) < yagoProperty.minCount and not (isSecondaryClass and predicate == Prefixes.rdfsLabel):
            debug("Min count", yagoProperty.minCount, "not satisfied for", mainEntity, predicate)
            return False
    return True

def guessLabelIfNecessary(entityFacts: Graph) -> bool:
    """ Tries to guess a label for an entity from a Wikipedia URL"""
    mainEntity: str = entityFacts.mainSubject()            
    if entityFacts.objectsOf(mainEntity, Prefixes.rdfsLabel):
        debug(mainEntity, "already has a label", entityFacts.objectsOf(mainEntity, Prefixes.rdfsLabel))
        return True
    wikipediaPages = entityFacts.objectsOf(mainEntity, Prefixes.schemaPage)
    labelName: Optional[str] = None
    labelLanguage: str = "en"
    for wikipediaPage in wikipediaPages:
        for (language, title) in re.findall("https://([a-z]+).wikipedia.org/wiki/([^^]*)", wikipediaPage):
            if language == "en" or not labelName:
                labelName = title            
                labelLanguage = language
    if labelName:        
        labelName = parse.unquote(labelName)
        labelName = re.sub("[\"'\u0000-\u001f]", "", labelName)
        if len(labelName) > Prefixes.MIN_LABEL_LENGTH:
            debug("Found label for", mainEntity, ": ", labelName)
            entityFacts.add((mainEntity, Prefixes.rdfsLabel, '"' + labelName + '"@' + labelLanguage))
            return True
    debug("Found no label for", mainEntity)
    return False
    
##########################################################################
#             Main method
##########################################################################
  
class treatWikidataEntity():
    """ Visitor that will handle every Wikidata entity """
    def __init__(self, workerId: int) -> None:
        """ We load everything once per process (!) in order to avoid problems with shared memory """
        print("    Initializing Wikidata reader", workerId+1, flush=True)
        self.number: int = workerId
        print("    Wikidata reader", workerId+1, "loads YAGO schema", flush=True)
        self.yagoSchema: YagoSchema = YagoSchema(FOLDER+"01-yago-final-schema.ttl", False)
        print("    Wikidata reader", workerId+1, "loads YAGO taxonomy", flush=True)
        self.yagoTaxonomyUp: Dict[str, Set[str]] = defaultdict(set)
        for triple in TsvUtils.tsvTuples(FOLDER+"02-yago-taxonomy-to-rename.tsv"):
            if len(triple) > 3:
                self.yagoTaxonomyUp[triple[0]].add(triple[2])
                
        print("    Done initializing Wikidata reader", workerId+1, flush=True)
        self.writer: Optional[TsvUtils.TsvFileWriter] = None
                
    def visit(self, entityFacts: Graph) -> None:
        """ Writes out the facts for a single Wikidata entity """
                    
        # We have to open the file here and not in init() to avoid pickling problems
        if not self.writer:
            self.writer = TsvUtils.TsvFileWriter(FOLDER+"03-yago-facts-to-type-check-"+(str(self.number).rjust(4,'0'))+".tmp")
            self.writer.__enter__()
                    
        handleWebPages(entityFacts)               

        # Wikidata classes that are mapped to a YAGO class, but that are not the first
        # among those mapped to the same YAGO class
        isSecondaryClass: bool = isSecondaryWikidataClass(entityFacts, self.yagoSchema)
        
        entityFacts, dates = translatePropertiesAndClasses(entityFacts, self.yagoSchema)
                    
        handleTypeAssertions(entityFacts, self.yagoTaxonomyUp)        
                
        types: Set[str] = handleAndReturnTypes(entityFacts, self.yagoSchema, self.yagoTaxonomyUp)
        
        handleDomain(entityFacts, self.yagoSchema, types)
        
        handleRange(entityFacts, self.yagoSchema)
        
        handleMaxCounts(entityFacts, self.yagoSchema, isSecondaryClass)

        if not isSecondaryClass and not guessLabelIfNecessary(entityFacts):
            debug("Label failed", entityFacts.mainSubject())
            return
        
        if not checkMinCounts(entityFacts, self.yagoSchema, isSecondaryClass):
            debug("Mincount failed", entityFacts.mainSubject())
            return
        
        subject: str = entityFacts.mainSubject()
        for predicate in entityFacts.predicatesOf(subject):
            for obj in entityFacts.objectsOf(subject, predicate):
                if subject == obj:
                    # Rare cases that are nonsense
                    continue
                if predicate == Prefixes.rdfType:
                    self.writer.write(subject, "rdf:type", obj, ".")
                    continue
                else:
                    yagoProperty = self.yagoSchema.properties[predicate]
                (startDate, endDate) = dates.get((subject, predicate, obj), (None, None))
                # Remove end date for alumni
                if predicate == Prefixes.schemaAlumniOf:
                    endDate = None
                if predicate == Prefixes.schemaDateCreated:
                    endDate = None
                    startDate = None
                if TurtleUtils.isLiteral(obj):
                    if startDate or endDate:
                        self.writer.write(subject, yagoProperty.identifier, obj, ". #", "", normalizeDate(startDate), normalizeDate(endDate))                
                    else:
                        self.writer.write(subject, yagoProperty.identifier, obj, ".")                
                else:
                    self.writer.write(subject, yagoProperty.identifier, obj, ". # IF", (", ".join(sorted(yagoProperty.objectTypes))), normalizeDate(startDate), normalizeDate(endDate))

    def result(self) -> None:
        if self.writer:
            self.writer.__exit__()
        return None
        
if __name__ == '__main__':
    with TsvUtils.Timer("Step 03: Creating YAGO facts"):
        TurtleUtils.visitWikidata(WIKIDATA_FILE, treatWikidataEntity) 
        print("  Collecting results...")
        count=0
        tempFiles=list(glob.glob(FOLDER+"03-yago-facts-to-type-check-*.tmp"))
        tempFiles.sort()
        with open(FOLDER+"03-yago-facts-to-type-check.tsv", "wb") as writer:
            for file in tempFiles:
                print("    Reading",file)
                with open(file, "rb") as reader:
                    for line in reader:
                        writer.write(line)
                        if not line.startswith(b"@"):
                            count+=1
        print("  done")
        print("  Info: Number of facts:",count)
        
        print("  Deleting temporary files...", end="", flush=True)
        for file in tempFiles:
            os.remove(file)
        print(" done")
    
    if TEST:
        Evaluator.compare(FOLDER+"03-yago-facts-to-type-check.tsv")