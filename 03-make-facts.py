"""
Creates the the YAGO facts from the Wikidata facts

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
import Evaluator
from Schema import YagoSchema
from collections import defaultdict

TEST=len(sys.argv)>1 and sys.argv[1]=="--test"
FOLDER="test-data/03-make-facts/" if TEST else "yago-data/"
WIKIDATA_FILE= "test-data/03-make-facts/00-wikidata.ttl" if TEST else "../wikidata.ttl"

##########################################################################
#             Debugging
##########################################################################

def debug(*message):
    """ Prints a message if we're in TEST mode"""
    if TEST:
        sys.stdout.buffer.write(b"  DEBUG: ")
        for m in message:
            # Using this instead of print to allow printing unicode chars to pipes
            sys.stdout.buffer.write(str(m).encode('utf8'))
            sys.stdout.buffer.write(b" ")
        print("")
    
def getFirst(myList):
    """ Returns the first element of an iterable or none """    
    for o in myList:
        return o
    return None
    
##########################################################################
#             Cleaning of entities
##########################################################################

def translatePropertiesAndClasses(entityFacts, yagoSchema):
    """ Replaces properties by their YAGO properties, and classes by their YAGO equivalents, returns new graph and fact dates """
    newGraph=Graph()
    dates={}
    for (s,p,o) in entityFacts:
        startDate, endDate=getStartAndEndDate(s, p, o, entityFacts)
        s=yagoSchema.wikidataProperties[s].identifier if s in yagoSchema.wikidataProperties else s
        p=yagoSchema.wikidataProperties[p].identifier if p in yagoSchema.wikidataProperties else p
        o=yagoSchema.wikidataProperties[o].identifier if o in yagoSchema.wikidataProperties else o
        s=yagoSchema.wikidataClasses[s].identifier if s in yagoSchema.wikidataClasses else s
        p=yagoSchema.wikidataClasses[p].identifier if p in yagoSchema.wikidataClasses else p
        o=yagoSchema.wikidataClasses[o].identifier if o in yagoSchema.wikidataClasses else o
        newGraph.add((s,p,o))
        if startDate or endDate:
            dates[(s,p,o)]=(startDate, endDate)
    return (newGraph, dates)
   
def handleWebPages(entityFacts):
    """ Changes <page, schema:about, entity> to <entity, mainEntityOfPage, page> """
    for s, p, o in entityFacts.triplesWithPredicate(Prefixes.schemaAbout):
        entityFacts.remove((s, Prefixes.schemaAbout, o))
        entityFacts.add((o, Prefixes.schemaPage, s))
        debug("Fixed",o, Prefixes.schemaPage, s)
    
def handleTypeAssertions(entityFacts, yagoTaxonomyUp):
    """Replace all facts <subject, wikidata:type, class> by <subject, rdf:type, class>"""
    # Given types are mostly meta stuff
    mainEntity=entityFacts.mainSubject()
    entityFacts.removeObjects(mainEntity,Prefixes.rdfType)
    for predicate in list(entityFacts.predicatesOf(mainEntity)):
        if predicate==Prefixes.wikidataType or predicate==Prefixes.wikidataOccupation:
            for obj in entityFacts.objectsOf(mainEntity, predicate):
                entityFacts.add((mainEntity,Prefixes.rdfType,obj))  
        # Anything that has a parent taxon is an instance of taxon
        if predicate=="schema:parentTaxon":
            entityFacts.add((mainEntity,Prefixes.rdfType,Prefixes.schemaTaxon))
    entityFacts.removeObjects(mainEntity,Prefixes.wikidataType)
    entityFacts.removeObjects(mainEntity,Prefixes.wikidataOccupation)
    # If you're a class, say it
    if mainEntity in yagoTaxonomyUp:
        entityFacts.add((mainEntity ,Prefixes.rdfType,Prefixes.rdfsClass))
        
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
    
def getStartAndEndDate(s, p, o, entityGraph):
    """ Returns a tuple of a start date and an end date for this fact.
        Unknown components are None. """
    # The property should be in the namespace WDT
    if not p.startswith("wdt:"):
        return (None, None)
    # Translate to the namespace P
    pStatement="p:"+p[4:]
    # Translate to the namespace PS
    pValue="ps:"+p[4:]
    if pStatement=="p:P1082": print("Get start date", s, p, o, pStatement, pValue, entityGraph)
    # Find all meta statements about (s, p, _)
    for statement in entityGraph.objectsOf(s, pStatement):
        # If the meta-statement concerns indeed the object o...
        if (statement, pValue, o) in entityGraph:
            # If there is a "duringTime" (pq:P585), return that one
            for duringTime in entityGraph.objectsOf(statement, Prefixes.wikidataDuring):
                if TurtleUtils.isDate(duringTime):
                    return (duringTime, duringTime)
                else:
                    debug("Removing bad date",duringTime)
            # Otherwise extract start time and end time
            startDate=getFirst(entityGraph.objectsOf(statement, Prefixes.wikidataStart))
            endDate=getFirst(entityGraph.objectsOf(statement, Prefixes.wikidataEnd))
            return(normalizeDate(startDate) if TurtleUtils.isDate(startDate) else None, normalizeDate(endDate) if TurtleUtils.isDate(endDate) else None)
    return (None, None)

##########################################################################
#             Taxonomy checks
##########################################################################

def handleAndReturnTypes(entityFacts, yagoSchema, yagoTaxonomyUp):
    """Removes disjoint classes and shortcuts, returns types"""
    mainEntity=entityFacts.mainSubject()
    superTypes=set()
    # Sort the list to make this deterministic
    directTypes=sorted(entityFacts.objectsOf(mainEntity, Prefixes.rdfType))
    for typ in directTypes:
        mySuperClasses=getSuperClasses(typ,yagoTaxonomyUp, set())
        for mySuperClass in mySuperClasses:
            if mySuperClass in yagoSchema.classes:
                for disjointYagoClass in yagoSchema.classes[mySuperClass].disjointWith:
                    if disjointYagoClass.identifier in superTypes or disjointYagoClass.identifier in directTypes: 
                        entityFacts.remove((mainEntity, Prefixes.rdfType, typ))
                        debug("Removed disjoint type", typ, "from", mainEntity,"since disjoint with",disjointYagoClass)
                        break
        else:
            mySuperClasses.remove(typ)
            superTypes.update(mySuperClasses)
            
    # Remove shortcuts        
    for typ in directTypes:
        if typ in superTypes:
            entityFacts.remove((mainEntity, Prefixes.rdfType, typ))
            debug("Removed shortcut type", typ, "from", mainEntity, superTypes)
    superTypes.update(directTypes)
    return superTypes    
    
def getSuperClasses(cls, yagoTaxonomyUp, classes):
    """Adds all superclasses of a class <cls> (including <cls>) to the set <classes>, returns it; start with empty classes set"""
    classes.add(cls)
    # Make a check before because it's a defaultdict,
    # which would create cls if it's not there
    if cls in yagoTaxonomyUp:
        for sc in yagoTaxonomyUp[cls]:
            getSuperClasses(sc, yagoTaxonomyUp, classes)
    return classes
        
##########################################################################
#             Handling domains and range
##########################################################################

def handleDomain(entityFacts, yagoSchema, fullTransitiveClasses):
    """ Performs a domain check, removes offending facts"""
    mainEntity=entityFacts.mainSubject()
    for predicate in list(entityFacts.predicatesOf(mainEntity)):
        if predicate==Prefixes.rdfType:
            continue
        yagoProperty=yagoSchema.properties.get(predicate, None)
        if not yagoProperty:
           entityFacts.removeObjects(mainEntity,predicate)
           debug("Removed unknown predicate",mainEntity,predicate)
           continue
        for obj in list(entityFacts.objectsOf(mainEntity, predicate)):
            if not any(c in fullTransitiveClasses for c in yagoProperty.subjectTypes):
                debug("Domain check failed for",mainEntity,yagoProperty, fullTransitiveClasses)
                entityFacts.remove((mainEntity, predicate, obj))
                     
def isURI(s): 
    """TRUE if s conforms to xsd:anyUri, as explained here:
    https://stackoverflow.com/questions/14466585/is-this-regex-correct-for-xsdanyuri """
    return not re.search("(%(?![0-9A-F]{2})|#.*#)", s)

def normalizeString(s):
    """ Makes sure that a string does not contain invalid characters or languages"""
    if not s or not s.startswith('"'):
        return s
    return s.replace("\uFFFD","_").replace('"@zh-classical','"@zh')

def normalizeDate(literal):
    """ Converts midnight dates to dates"""
    return re.sub('T00:00:00Z"\\^\\^xsd:dateTime$','"^^xsd:date', literal) if literal else None
    
def cleanLiteralObject(obj,datatype):
    """ Returns a version of obj that corresponds to the datatype -- or None"""
    if datatype==Prefixes.xsdAnytype:
        return obj if obj.startswith('"') else None
    if datatype==Prefixes.xsdAnyURI and obj.startswith('<'):
        obj=obj[1:-1]
        if not isURI(obj):
            return None
        return '"'+obj+'"^^xsd:anyURI'
    if datatype==Prefixes.xsdString and obj.startswith('<'):
        return '"'+obj[1:-1]+'"'       
    literalValue, _, lang, literalDataType = TurtleUtils.splitLiteral(obj)
    if literalValue is None:
        return None
    if datatype==Prefixes.xsdAnyURI:
        return '"'+literalValue+'"^^'+Prefixes.xsdAnyURI if isURI(literalValue) else None
    if datatype==Prefixes.xsdString:
        return '"'+literalValue+'"'
    if datatype==Prefixes.rdfLangString:
        return obj if literalDataType is None and lang is not None else None
    if datatype==Prefixes.xsdDateTime:
        # Erroneous default dates in Wikidata
        if obj.startswith('"0000'):
           return None
        # Strings that are longer than any possible date   
        if len(obj)>len('"+0000-01-01T00:00:00Z"^^xsd:dateTime'):
           return None
        # Fall through
    return obj if literalDataType==datatype else None
        
def cleanObject(obj, yagoProperty):
    """Returns an object that conforms to the range of the yagoProperty -- or None in case of failure"""
    # Patterns are verified in a fall-through fashion,
    # because verifying a pattern is a necessary but not sufficient condition
    if yagoProperty.pattern:
       objectValue=TurtleUtils.splitLiteral(obj)[0]
       if objectValue is None:
           debug("Object is not a literal",obj)
           return None
       if not re.match(yagoProperty.pattern, objectValue):
            debug("Object does not match regex:",objectValue, yagoProperty.pattern)
            return None
    
    # TRUE if this type admits entity objects (as opposed to literals)
    couldBeEntity=False
    
    for objectType in yagoProperty.objectTypes:
        if objectType.startswith("xsd:") or objectType.startswith("rdf:") or objectType.startswith("geo:"):
            newObj=cleanLiteralObject(obj, objectType)
            if newObj:
                return normalizeDate(normalizeString(newObj))
        else:
            couldBeEntity=True
            
    # If the object is a literal, there is no chance we can make it fit the range
    if TurtleUtils.isLiteral(obj):
        debug("Could not match any object type for", obj,yagoProperty.objectTypes)
        return None
    
    # If the object is not a literal, it can still work if we allow entities
    return obj if couldBeEntity else None

def handleRange(entityFacts, yagoSchema):
    """ Performs a range check, removes offending facts"""
    mainEntity=entityFacts.mainSubject()
    for predicate in list(entityFacts.predicatesOf(mainEntity)):
        yagoProperty=yagoSchema.properties.get(predicate, None)
        if not yagoProperty:
           continue 
        for obj in list(entityFacts.objectsOf(mainEntity, predicate)):
            cleanObj=normalizeDate(normalizeString(cleanObject(obj, yagoProperty)))
            if cleanObj is None:
                entityFacts.remove((mainEntity, predicate, obj))
                debug("Range check failed for",obj,yagoProperty, yagoProperty.objectTypes)
            elif cleanObj!=obj:
                debug("Cleaned object",obj,cleanObj)
                entityFacts.remove((mainEntity, predicate, obj))         
                entityFacts.add((mainEntity, predicate, cleanObj))
                

##########################################################################
#             Handling max counts
##########################################################################

def isSecondaryWikidataClass(entityFacts, yagoSchema):
    """ TRUE if entityFacts describe a class that is mapped to a YAGO class, and this class is not the first among them"""
    mainEntity=entityFacts.mainSubject()
    if mainEntity in yagoSchema.wikidataClasses:
        candidates=list(yagoSchema.wikidataClasses[mainEntity].fromClasses)
        candidates.sort()
        debug("Is Wikidata class",mainEntity,candidates)
        return mainEntity!=candidates[0]
    return False

def handleMaxCounts(entityFacts, yagoSchema, isSecondaryClass=False):
    """ Performs uniqueLang and maxCount checks, removes offending facts """
    mainEntity=entityFacts.mainSubject()            
    for predicate in list(entityFacts.predicatesOf(mainEntity)):        
        yagoProperty=yagoSchema.properties.get(predicate, None)
        if not yagoProperty:
            continue
        # For secondary classes, we do not add anything that might violate maxcounts
        if isSecondaryClass and (yagoProperty.maxCount or yagoProperty.uniqueLang):
            debug("Secondary class",mainEntity,"loses",predicate)
            entityFacts.removeObjects(mainEntity,predicate)
            continue
        # Check maxcount    
        if yagoProperty.maxCount and len(entityFacts.objectsOf(mainEntity, predicate))>yagoProperty.maxCount:
            objects=list(entityFacts.objectsOf(mainEntity, predicate))
            objects.sort()
            for i in range(yagoProperty.maxCount, len(objects)):
                entityFacts.remove((mainEntity, predicate, objects[i]))
        # Check unique languages
        if yagoProperty.uniqueLang:
            languages=set()
            objects=list(entityFacts.objectsOf(mainEntity, predicate))
            objects.sort(key=len)
            objects.reverse()
            debug("Unique language for",mainEntity,yagoProperty, objects)
            if not objects:
                debug("No objects:",mainEntity, predicate, objects)
                continue
            for obj in objects:
                _,_,lang,_=TurtleUtils.splitLiteral(obj)
                if lang:
                   if lang in languages:
                        debug("Duplicate language:",mainEntity,predicate,lang)
                        entityFacts.remove((mainEntity, predicate, obj))
                   else:
                        languages.add(lang)


##########################################################################
#             Main method
##########################################################################
  
class treatWikidataEntity():
    """ Visitor that will handle every Wikidata entity """
    def __init__(self,i):
        """ We load everything once per process (!) in order to avoid problems with shared memory """
        print("    Initializing Wikidata reader",i+1, flush=True)
        self.number=i
        print("    Wikidata reader",i+1, "loads YAGO schema", flush=True)
        self.yagoSchema=YagoSchema(FOLDER+"01-yago-final-schema.ttl")
        print("    Wikidata reader",i+1, "loads YAGO taxonomy", flush=True)
        self.yagoTaxonomyUp=defaultdict(set)
        for triple in TsvUtils.tsvTuples(FOLDER+"02-yago-taxonomy-to-rename.tsv"):
            if len(triple)>3:
                self.yagoTaxonomyUp[triple[0]].add(triple[2])
                
        print("    Done initializing Wikidata reader",i+1, flush=True)
        self.writer=None
                
    def visit(self,entityFacts):
        """ Writes out the facts for a single Wikidata entity """
                    
        # We have to open the file here and not in init() to avoid pickling problems
        if not self.writer:
            self.writer=TsvUtils.TsvFileWriter(FOLDER+"03-yago-facts-to-type-check-"+(str(self.number).rjust(4,'0'))+".tmp")
            self.writer.__enter__()
                    
        handleWebPages(entityFacts)               

        # Wikidata classes that are mapped to a YAGO class, but that are not the first
        # among those mapped to the same YAG class
        isSecondaryClass=isSecondaryWikidataClass(entityFacts, self.yagoSchema)
        
        entityFacts, dates=translatePropertiesAndClasses(entityFacts, self.yagoSchema)
        
        print(entityFacts, dates)
        
        handleTypeAssertions(entityFacts, self.yagoTaxonomyUp)        
                
        types=handleAndReturnTypes(entityFacts, self.yagoSchema, self.yagoTaxonomyUp)
        
        handleDomain(entityFacts, self.yagoSchema, types)
        
        handleRange(entityFacts, self.yagoSchema)
        
        handleMaxCounts(entityFacts, self.yagoSchema, isSecondaryClass)
        
        s=entityFacts.mainSubject()
        for p in entityFacts.predicatesOf(s):
            for o in entityFacts.objectsOf(s,p):
                if s==o:
                    # Rare cases that are nonsense
                    continue
                if p==Prefixes.rdfType:
                    self.writer.write(s,"rdf:type",o,".")
                    continue
                else:
                    yagoProperty = self.yagoSchema.properties[p]
                (startDate, endDate) = dates.get((s, p, o), (None, None))
                # Remove end date for alumni
                if p=="schema:alumniOf":
                    endDate=None
                if p=="schema:dateCreated":
                    endDate=None
                    startDate=None
                if TurtleUtils.isLiteral(o):
                    if startDate or endDate:
                        self.writer.write(s,yagoProperty.identifier,o, ". #", "", normalizeDate(startDate), normalizeDate(endDate))                
                    else:
                        self.writer.write(s,yagoProperty.identifier,o, ".")                
                else:
                    self.writer.write(s,yagoProperty.identifier,o,". # IF",(", ".join(sorted(yagoProperty.objectTypes))), normalizeDate(startDate), normalizeDate(endDate))

    def result(self):
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