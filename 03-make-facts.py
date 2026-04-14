"""
Creates the YAGO facts from the Wikidata facts

CC-BY 2022-2025 Fabian M. Suchanek

Call:
  python3 make-facts.py

Input:
- 01-yago-final-schema.ttl
- 02-yago-taxonomy-to-rename.tsv
- Wikidata file in input-data/wikidata.ttl

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
WIKIDATA_FILE= "test-data/03-make-facts/00-wikidata.ttl" if TEST else "input-data/wikidata.ttl"

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
    
def getFirst(iterable: Iterator[Any], default=None) -> Optional[Any]:
    """ Returns the first element of an iterable or None"""
    if iterable is None:
        return None
    return next(iter(iterable), default)
    
##########################################################################
#             Cleaning of entities
##########################################################################

def translatePropertiesAndClasses(entityFacts: Graph, yagoSchema: YagoSchema) -> Tuple[Graph, Dict[Tuple[str, str, str], Tuple[Optional[str], Optional[str]]]]:
    """ Replaces properties by their YAGO properties, and classes by their YAGO equivalents, returns new graph and fact dates and fact units"""
    newGraph: Graph = Graph()
    dates: Dict[Tuple[str, str, str], Tuple[Optional[str], Optional[str]]] = {}
    unitsOfMeasurement = {}
    for (subject, predicate, obj) in entityFacts:
        # Get meta properties
        startDate, endDate = getStartAndEndDate(subject, predicate, obj, entityFacts)
        unit=getUnitOfMeasurement(subject, predicate, obj, entityFacts)
        
        # Translate subject and object
        if subject in yagoSchema.wikidataProperties:
            subject = getFirst(yagoSchema.wikidataProperties[subject]).identifier
        if subject in yagoSchema.wikidataClasses:
            subject = yagoSchema.wikidataClasses[subject].identifier
        if obj in yagoSchema.wikidataProperties:
            obj = getFirst(yagoSchema.wikidataProperties[obj]).identifier
        if obj in yagoSchema.wikidataClasses:
            obj = yagoSchema.wikidataClasses[obj].identifier
        
        # Translate predicate
        # One Wikidata property can map to several YAGO properties
        predicateList=[p.identifier for p in yagoSchema.wikidataProperties[predicate]] if predicate in yagoSchema.wikidataProperties else [predicate]
        for p in predicateList:
            newGraph.add((subject, p, obj))
            if startDate or endDate:
                dates[(subject, p, obj)] = (startDate, endDate)
            if unit:
                unitsOfMeasurement[(subject, p, obj)] = unit
    return (newGraph, dates, unitsOfMeasurement)
   
def handleWebPages(entityFacts: Graph) -> None:
    """ Changes <page, schema:about, entity> to <entity, url, page> """
    for page, predicate, entity in entityFacts.triplesWithPredicate(Prefixes.schemaAbout):
        entityFacts.remove((page, Prefixes.schemaAbout, entity))
        entityFacts.add((entity, Prefixes.schemaUrl, page))
        debug("Fixed", entity, Prefixes.schemaUrl, page)

# Predicates that generate a class membership
TYPE_PREDICATES=[Prefixes.wikidataType, Prefixes.wikidataOccupation, Prefixes.wikidataGenre, Prefixes.wikidataPosition]
    
def translateTypeAssertions(entityFacts: Graph, yagoTaxonomyUp: Dict[str, Set[str]]):
    """Replace all facts <subject, wikidata:type, class> by <subject, rdf:type, class>, returns Wikidata types"""
    # Given types are mostly meta stuff
    mainEntity: str = entityFacts.mainSubject()
    entityFacts.removeObjects(mainEntity, Prefixes.rdfType)
    declaredWikidataTypes=set()
    # If you're a class, say it
    if mainEntity in yagoTaxonomyUp:
        entityFacts.add((mainEntity, Prefixes.rdfType, Prefixes.rdfsClass))
        return declaredWikidataTypes
    # Translate all type-generating predicates to an rdf:type fact    
    for predicate in TYPE_PREDICATES:
        if predicate in entityFacts.predicatesOf(mainEntity):
            for obj in entityFacts.objectsOf(mainEntity, predicate):
                if obj in yagoTaxonomyUp:
                    if predicate==Prefixes.wikidataType:
                        declaredWikidataTypes.add(obj)
                    else:
                        debug("Adding type",obj,"from",predicate)
                    entityFacts.add((mainEntity, Prefixes.rdfType, obj))
            entityFacts.removeObjects(mainEntity, predicate)
    # Anything that has a parent taxon is an instance of taxon
    if Prefixes.schemaParentTaxon in entityFacts.predicatesOf(mainEntity):
        entityFacts.add((mainEntity, Prefixes.rdfType, Prefixes.schemaTaxon))
    return declaredWikidataTypes
    
##########################################################################
#             Ranks
##########################################################################

# Ranks are encoded as follows in Wikidata:
#
# # Belgium has 11m inhabitants
# wd:Q31 wdt:P1082 "+11431406"^^xsd:decimal .
# wd:Q31 p:P1082 wds:Q31-a01a7f7f-41c6-f3b6-1782-64db48331257 .
# wds:Q31-a01a7f7f-41c6-f3b6-1782-64db48331257 a wikibase:Statement,
#                wikibase:BestRank ;
#        wikibase:rank wikibase:PreferredRank ;
#        ps:P1082 "+11825551"^^xsd:decimal ;
        
def addNonBestRanks(entityFacts, yagoSchema):
    """ Adds all non-best facts for type generators"""
    subject=entityFacts.mainSubject()
    for statement in entityFacts.subjectsOf("wikibase:rank", "wikibase:NormalRank"):
        if (statement, Prefixes.rdfType, "wikibase:BestRank") not in entityFacts:
            for predicate in entityFacts.predicatesOf(statement):
                if predicate.startswith("ps:"):
                    wikidataPredicate="wdt:"+predicate[3:]
                    if wikidataPredicate not in TYPE_PREDICATES:
                        debug("Not adding non-best fact because it's not type generating:",subject, wikidataPredicate, statement)
                        continue
                    for obj in entityFacts.objectsOf(statement, predicate):
                        debug("Adding non-best fact:",subject, wikidataPredicate, obj, statement)
                        entityFacts.add((subject, wikidataPredicate, obj))

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
#             Measurement Units
##########################################################################

# Measurememt Units are encoded as follows in Wikidata:

# The subject has width 229
# wd:Q412 wdt:P2049 "+229"^^xsd:decimal ;
# wd:Q412 p:P2049 wds:Q412-f59c2424-4d7b-9af6-e603-10f97367f37d .
# wds:Q412-f59c2424-4d7b-9af6-e603-10f97367f37d a wikibase:Statement,
#        ps:P2049 "+229"^^xsd:decimal ;
#        psv:P2049 wdv:c2a949c9af32533b2e84ae206053067e ;
# wdv:c2a949c9af32533b2e84ae206053067e a wikibase:QuantityValue ;
#        wikibase:quantityAmount "+229"^^xsd:decimal ;
#        wikibase:quantityUnit <http://www.wikidata.org/entity/Q174789> .

def getUnitOfMeasurement(subject, predicate, obj, entityGraph):
    """ Returns the unit of measurement of this fact as a Wikidata entity """
    # Get wds-object
    if not predicate.startswith("wdt:"):
        return None
    for wdsObject in entityGraph.objectsOf(subject, "p:"+predicate[4:]):
        if obj in entityGraph.objectsOf(wdsObject, "ps:"+predicate[4:]):
            # get wdv object
            for wdvObject in entityGraph.objectsOf(wdsObject, "psv:"+predicate[4:]):
                for unit in entityGraph.objectsOf(wdvObject, Prefixes.wikibaseQuantityUnit):
                    debug("Found unit", subject, predicate, obj, unit)
                    return "wd:"+unit[unit.rfind('/')+1:-1]
    return None
    
##########################################################################
#             Taxonomy checks
##########################################################################

def cleanAndReturnTypes(entityFacts: Graph, yagoSchema: YagoSchema, yagoTaxonomyUp: Dict[str, Set[str]], writer, declaredWikidataTypes) -> Set[str]:
    """Removes disjoint classes and shortcuts, returns super types"""
    mainEntity: str = entityFacts.mainSubject()
    myTypesAndSuperTypes: Set[str] = set()
    # Sort the list to make this deterministic
    directTypes: List[str] = sorted(entityFacts.objectsOf(mainEntity, Prefixes.rdfType))
    for i in range(0,len(directTypes)):
        directType=directTypes[i]
        # Remove type if I am a shortcut
        if directType in myTypesAndSuperTypes:
            entityFacts.remove((mainEntity, Prefixes.rdfType, directType))
            if directType in declaredWikidataTypes:
                writer.writeMetaFact(mainEntity, Prefixes.rdfType, directType, Prefixes.ysReason, f'"is shortcut"')
            continue               
        # Remove disjoint types
        superClasses: Set[str] = getSuperClasses(directType, yagoTaxonomyUp, set())
        gotRemoved=False
        for superClass in superClasses:
            if superClass in yagoSchema.classes:
                for disjointClass in yagoSchema.classes[superClass].disjointWith:
                    if disjointClass.identifier in myTypesAndSuperTypes:
                        entityFacts.remove((mainEntity, Prefixes.rdfType, directType))
                        if directType in declaredWikidataTypes:
                            writer.writeMetaFact(mainEntity, Prefixes.rdfType, directType, Prefixes.ysReason, f'"disjoint with {disjointClass}"')
                        gotRemoved=True
                        break
                if gotRemoved:
                    break
        if gotRemoved:
            continue
        # Remove other type if the other one is a shortcut
        for j in range(0,i):
            if directTypes[j] in superClasses: 
                entityFacts.remove((mainEntity, Prefixes.rdfType, directTypes[j]))
                if directTypes[j] in declaredWikidataTypes:
                    writer.writeMetaFact(mainEntity, Prefixes.rdfType, directTypes[j], Prefixes.ysReason, f'"is shortcut"')                
        # The class is OK
        myTypesAndSuperTypes.update(superClasses)
    return myTypesAndSuperTypes
    
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

def handleDomain(entityFacts: Graph, yagoSchema: YagoSchema, fullTransitiveClasses: Set[str], writer) -> None:
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
        if fullTransitiveClasses.isdisjoint(yagoProperty.subjectTypes):
            # Remove all objects for this predicate if domain check fails
            writer.writeMetaFact(mainEntity, yagoProperty.identifier, Prefixes.schemaThing, Prefixes.ysReason, f'"Domain check failed, subject is {", ".join(s for s in fullTransitiveClasses if not s.startswith("wd:") and s!=Prefixes.schemaThing)} and expected types are {", ".join(yagoProperty.subjectTypes)}"')
            entityFacts.removeObjects(mainEntity, predicate)
                     
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
    if not literal:
        return None
    # Remove zero date    
    literal = re.sub('T00:00:00Z"\\^\\^xsd:dateTime$', '"^^xsd:date', literal)
    # Remove first of January, because this often means just any date in the year.
    # Wikidata does model the time precision, but the wdv-object is not co-located with
    # the facts itself, making it hard to recover.
    literal = re.sub('-01-01"\\^\\^xsd:date$', '"^^xsd:gYear', literal)
    return literal

DATE_REGEX=r'[+-]?[0-9]{1,4}-[0-9]{1,2}-[0-9]{1,2}(T[0-9]{1,2}:[0-9]{1,2}:[0-9]{1,2}(\\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})?)?'

INT_REGEX=r"\+?(-?[0-9]+)(\.[0-9]+)?"

def cleanLiteralObject(obj: str, datatype: str) -> Optional[str]:
    """ Returns a version of obj that corresponds to the datatype -- or None"""
    if datatype == Prefixes.xsdAnytype:
        return obj if obj.startswith('"') else None
    if datatype == Prefixes.xsdAnyURI and obj.startswith('<'):
        obj = obj[1:-1]
        if not isURI(obj):
            return None
        return '"' + obj + '"^^xsd:anyURI'
    # See if we can cast this to a string
    if datatype == Prefixes.xsdString:
        if obj.startswith('<'):
            return '"' + obj[1:-1] + '"'   
        if obj.startswith('yago:'):
            return '"' + obj[5:] + '"'   
        if obj.startswith('wd:'):
            return '"' + Prefixes.REPLACE_QID_FLAG + obj + '"'   
    literalValue, _, lang, literalDataType = TurtleUtils.splitLiteral(obj)
    if literalValue is None:
        return None
    if datatype == Prefixes.xsdAnyURI:
        return '"' + literalValue + '"^^' + Prefixes.xsdAnyURI if isURI(literalValue) else None
    if datatype == Prefixes.xsdString:
        return '"' + literalValue.replace("’","'")+'"' # For entities like "Monty Python's Life of Brian"
    if datatype == Prefixes.rdfLangString:
        return obj.replace("’","'") if literalDataType is None and lang is not None else None
    if datatype == Prefixes.xsdDecimal and literalDataType == Prefixes.xsdInteger:
        return '"'+literalValue+'"^^'+Prefixes.xsdDecimal
    if datatype == Prefixes.xsdInteger:
        match=re.fullmatch(INT_REGEX,literalValue)
        if match:
            return f'"{match.group(1)}"^^{Prefixes.xsdInteger}'
        return None
    if datatype == Prefixes.xsdDateTime:
        # Erroneous default dates in Wikidata
        if obj.startswith('"0000'):
           return None
        # Strings that are bad dates
        if not re.fullmatch(DATE_REGEX,literalValue):
           return None
        # Fall through
    # Any decimals are OK for units of measurement
    if datatype.startswith(Prefixes.yagoUnit):
        if literalDataType is None or literalDataType!=Prefixes.xsdDecimal:
            return None
        return obj
    return obj if literalDataType == datatype else None
        
def cleanObject(subject, obj: str, yagoProperty: Any, writer) -> Optional[str]:
    """Returns an object that conforms to the range of the yagoProperty -- or None in case of failure. Returns normalized object (normalized string and date) ready for use."""
    
    # The currency of a country must be a currency, but not a literal
    if yagoProperty.identifier==Prefixes.yagoCurrency:
        if obj.startswith('"'):
            return None
        return obj
        
    # Patterns are verified in a fall-through fashion,
    # because verifying a pattern is a necessary but not sufficient condition
    if yagoProperty.pattern:
       objectValue = TurtleUtils.splitLiteral(obj)[0]
       if objectValue is None:
           writer.writeMetaFact(subject, yagoProperty.identifier, obj, Prefixes.ysReason, '"not a literal"')
           return None
       if not re.match(yagoProperty.pattern, objectValue):
           writer.writeMetaFact(subject, yagoProperty.identifier, obj, Prefixes.ysReason, '"pattern check failed"')
           return None
    
    # TRUE if this type admits entity objects (as opposed to literals)
    couldBeEntity: bool = False
    
    for objectType in yagoProperty.objectTypes:
        if objectType.startswith("xsd:") or objectType.startswith("rdf:") or objectType.startswith("geo:") or objectType.startswith(Prefixes.yagoUnit):
            cleanedObj = cleanLiteralObject(obj, objectType)
            if cleanedObj:
                # Normalize string and date - this is the only place normalization happens
                return normalizeDate(normalizeString(cleanedObj))
        else:
            couldBeEntity = True
            
    # If the object is a literal, there is no chance we can make it fit the range
    if TurtleUtils.isLiteral(obj):
        writer.writeMetaFact(subject, yagoProperty.identifier, obj, Prefixes.ysReason, '"uncastable literal"')
        return None
    
    # If the object is not a literal, it can still work if we allow entities
    if couldBeEntity:
         return obj
    # This happens mainly for datasets, so no need to write a log entry     
    debug(obj, "is not a literal as expected for",yagoProperty.identifier) 
    return None

def handleRange(entityFacts: Graph, yagoSchema: YagoSchema, writer) -> None:
    """ Performs a range check, removes offending facts"""
    mainEntity: str = entityFacts.mainSubject()
    for predicate in list(entityFacts.predicatesOf(mainEntity)):
        yagoProperty = yagoSchema.properties.get(predicate, None)
        if not yagoProperty:
           continue 
        for obj in list(entityFacts.objectsOf(mainEntity, predicate)):
            cleanObj = cleanObject(mainEntity, obj, yagoProperty, writer)
            if cleanObj is None:
                # Reason was already written to the writer
                entityFacts.remove((mainEntity, predicate, obj))
                continue
            if yagoProperty.minInclusive is not None or yagoProperty.maxInclusive is not None:
                splitObj=TurtleUtils.splitLiteral(cleanObj)
                if splitObj[0] is None or not re.match(r"[-+]?[0-9.]", splitObj[0]):
                    writer.writeMetaFact(mainEntity, yagoProperty.identifier, cleanObj, Prefixes.ysReason, '"not a number"')
                    entityFacts.remove((mainEntity, predicate, obj))
                    continue
                objValue=float(splitObj[0])
                if yagoProperty.minInclusive is not None and objValue<yagoProperty.minInclusive or yagoProperty.maxInclusive is not None and objValue>yagoProperty.maxInclusive:
                    writer.writeMetaFact(mainEntity, yagoProperty.identifier, cleanObj, Prefixes.ysReason, '"not in min-max range"')
                    entityFacts.remove((mainEntity, predicate, obj))
                    continue
            if cleanObj != obj:
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

def handleMaxCounts(entityFacts: Graph, yagoSchema: YagoSchema, writer, isSecondaryClass: bool = False) -> None:
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
                writer.writeMetaFact(mainEntity, predicate, objects[i], Prefixes.ysReason, '"maxcount overflow"')
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
                        # Generates too many exclusions that come from synonymous predicates 
                        # writer.writeMetaFact(mainEntity, predicate, obj, Prefixes.ysReason, f'"duplicate language: {lang}"')                                       
                        entityFacts.remove((mainEntity, predicate, obj))
                   else:
                        languages.add(lang)

# Pattern for astronomical object names
astro=r'"[-+A-Z0-9\[\] ]{3,} [JBF]?[-0-9.+]{6,}"@mul'

def guessLabelIfNecessary(entityFacts: Graph, writer) -> bool:
    """ Tries to guess a label for an entity from a Wikipedia URL"""
    mainEntity: str = entityFacts.mainSubject()            
    for l in entityFacts.objectsOf(mainEntity, Prefixes.rdfsLabel):
        if re.match(astro,l): 
            writer.writeMetaFact(mainEntity, Prefixes.rdfType, Prefixes.schemaThing, Prefixes.ysReason, f'"has invalid name: {l[1:9]}..."')
            return False
    if entityFacts.objectsOf(mainEntity, Prefixes.rdfsLabel):   
        debug(mainEntity, "already has a label", entityFacts.objectsOf(mainEntity, Prefixes.rdfsLabel))
        return True
    wikipediaPages = entityFacts.objectsOf(mainEntity, Prefixes.schemaUrl)
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
        if len(labelName) > 3:
            debug("Found label for", mainEntity, ": ", labelName)
            entityFacts.add((mainEntity, Prefixes.rdfsLabel, '"' + labelName + '"@' + labelLanguage))
            return True
    writer.writeMetaFact(mainEntity, Prefixes.rdfType, Prefixes.schemaThing, Prefixes.ysReason, '"no label"')
    return False
    
##########################################################################
#             Main method
##########################################################################
  
class treatWikidataEntity():
    """ Visitor that will handle every Wikidata entity """
    def __init__(self, workerId: int) -> None:
        """ We load everything once per process (!) in order to avoid problems with shared memory """
        self.number: int = workerId
        self.yagoSchema: YagoSchema = YagoSchema(FOLDER+"01-yago-final-schema.ttl", False)
        self.yagoTaxonomyUp: Dict[str, Set[str]] = defaultdict(set)
        for triple in TsvUtils.tsvTuples(FOLDER+"02-yago-taxonomy-to-rename.tsv"):
            if len(triple) > 3:
                self.yagoTaxonomyUp[triple[0]].add(triple[2])                
        self.writer: Optional[TsvUtils.TsvFileWriter] = None
                
    def visit(self, entityFacts: Graph) -> None:
        """ Writes out the facts for a single Wikidata entity """
                    
        # We have to open the file here and not in init() to avoid pickling problems
        if not self.writer:
            self.writer = TsvUtils.TsvFileWriter(FOLDER+"03-yago-facts-to-type-check-"+(str(self.number).rjust(4,'0'))+".tmp")
            self.writer.__enter__()
        
        handleWebPages(entityFacts)               

        addNonBestRanks(entityFacts, self.yagoSchema)
        
        # We backup the existing Wikidata types for the log messages
        oldTypes = entityFacts.objectsOf(entityFacts.mainSubject(), Prefixes.wikidataType)

        # Wikidata classes that are mapped to a YAGO class, but that are not the first
        # among those mapped to the same YAGO class
        isSecondaryClass: bool = isSecondaryWikidataClass(entityFacts, self.yagoSchema)
        
        entityFacts, dates, unitsOfMeasurement = translatePropertiesAndClasses(entityFacts, self.yagoSchema)
                
        declaredWikidataTypes = translateTypeAssertions(entityFacts, self.yagoTaxonomyUp)        
                
        types = cleanAndReturnTypes(entityFacts, self.yagoSchema, self.yagoTaxonomyUp, self.writer, declaredWikidataTypes)
        
        if not types:
            self.writer.writeMetaFact(entityFacts.mainSubject(), Prefixes.rdfType, Prefixes.schemaThing, Prefixes.ysReason, f'"no valid type among {", ".join(str(s) for s in oldTypes)}"')
            return True
        
        handleDomain(entityFacts, self.yagoSchema, types, self.writer)
                        
        handleRange(entityFacts, self.yagoSchema, self.writer)

        handleMaxCounts(entityFacts, self.yagoSchema, self.writer, isSecondaryClass)

        if not isSecondaryClass and not guessLabelIfNecessary(entityFacts, self.writer):
            return True       
        
        # Get the subject only here, because it might have changed by mapping to YAGO schema
        subject=entityFacts.mainSubject()                
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
                    targetDataType=getFirst(yagoProperty.objectTypes)
                    if targetDataType.startswith(Prefixes.yagoUnit):
                        unit=unitsOfMeasurement.get((subject, predicate, obj), None)
                        if unit:
                            obj = obj.replace(Prefixes.xsdDecimal, unit)
                if startDate or endDate:
                    self.writer.write(subject, yagoProperty.identifier, obj, ". #", normalizeDate(startDate), normalizeDate(endDate))                
                else:
                    self.writer.write(subject, yagoProperty.identifier, obj, ".")
        return True
        
    def result(self) -> None:
        if self.writer:
            self.writer.__exit__()
        return None
        
if __name__ == '__main__':
    with TsvUtils.Timer("Step 03: Creating YAGO facts"):
        TurtleUtils.visitWikidata(WIKIDATA_FILE, treatWikidataEntity) 
        print("  Collecting results...", end='', flush=True)
        factCount=0
        tempFiles=list(glob.glob(FOLDER+"03-yago-facts-to-type-check-*.tmp"))
        tempFiles.sort()
        with open(FOLDER+"03-yago-facts-to-type-check.log", "wb") as logWriter:        
            with open(FOLDER+"03-yago-facts-to-type-check.tsv", "wb") as writer:
                for file in tempFiles:
                    with open(file, "rb") as reader:
                        for line in reader:
                            if line.startswith(b"<<"):
                                logWriter.write(line)
                            elif line.strip():
                                writer.write(line)
                                if not line.startswith(b"@"):
                                    factCount+=1
        print("  done")
        print("  Info: Number of facts:",factCount)
        
        print("  Deleting temporary files...", end="", flush=True)
        for file in tempFiles:
            os.remove(file)
        print(" done")
    
    if TEST:
        Evaluator.compare(FOLDER+"03-yago-facts-to-type-check.tsv")