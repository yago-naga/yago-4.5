"""
Creates the the YAGO facts from the Wikidata facts

(c) 2022 Fabian M. Suchanek

Call:
  python3 make-facts.py

Input:
- 01-yago-schema.ttl
- 02-yago-taxonomy.tsv
- 02-non-yago-classes.tsv
- Wikidata file

Output:
- 03-yago-facts-to-type-check.tsv

Algorithm:
- run through all entities of Wikidata, with its associated facts
  - translate wikidata classes to YAGO classes
  - check for disjointness of classes
  - check cardinality constraints
  - check domain constraint
  - check range constraints
  - write out facts that fulfill the constraints to yago-facts-to-type-check.tsv  
"""

TEST=True
FOLDER="test-data/03-make-facts/" if TEST else "yago-data/"
WIKIDATA_FILE= "test-data/03-make-facts/00-wikidata.ttl" if TEST else "input-data/wikidata.ttl"

##########################################################################
#             Debugging
##########################################################################

def debug(*message):
    """ Prints a message if we're in TEST mode"""
    if TEST:
        for m in message:
            # Using this instead of print to allow printing unicode chars to pipes
            sys.stdout.buffer.write(str(m).encode('utf8'))
        print("")
    
##########################################################################
#             Booting
##########################################################################

print("Creating YAGO facts...")
print("  Importing...",end="", flush=True)
# Importing alone takes so much time that a status message is in order...
import Prefixes
import TsvUtils
import TurtleUtils
from TurtleUtils import Graph
import sys
import re
import evaluator
from collections import defaultdict
print("done")

yagoSchema=Graph()
yagoSchema.loadTurtleFile(FOLDER+"01-yago-schema.ttl", "  Loading YAGO schema")
disjointClasses=[ (c1, c2) for (c1, p, c2) in yagoSchema.triplesWithPredicate(Prefixes.owlDisjointWith) ]

yagoTaxonomyUp=defaultdict(set)
for triple in TsvUtils.tsvTuples(FOLDER+"02-yago-taxonomy.tsv", "  Loading YAGO taxonomy"):
    if len(triple)>3:
        yagoTaxonomyUp[triple[0]].add(triple[2])

nonYagoClasses={}
for triple in TsvUtils.tsvTuples(FOLDER+"02-non-yago-classes.tsv", "  Loading non-YAGO classes"):
    if len(triple)>3:
        nonYagoClasses[triple[0]]=triple[2]

def getFirst(myList):
    """ Returns the first element of a list or None """    
    return myList[0] if myList else None
    
##########################################################################
#             Cleaning of entities
##########################################################################

def cleanArticles(entityFacts):
    """ Changes <page, schema:about, entity> to <entity, mainentityOfPage, page> """
    for s, p, o in entityFacts.triplesWithPredicate(Prefixes.schemaAbout):
        entityFacts.remove((s, Prefixes.schemaAbout, o))
        entityFacts.add((o, Prefixes.schemaPage, s))
                
def checkIfClass(entityFacts):
    """Adds <subject, rdf:type, rdfs:Class> if this is a class. Removes all other type relationships. Returns new entityFacts."""
    if not entityFacts.triplesWithPredicate(Prefixes.rdfsLabel):
        return entityFacts
    mainEntity=entityFacts.subjects(Prefixes.rdfsLabel)[0]
    if any(yagoSchema.subjects(Prefixes.fromClass, mainEntity)):
        entityFacts.add((mainEntity,Prefixes.rdfType,Prefixes.rdfsClass))
        yagoClass=yagoSchema.subjects(Prefixes.fromClass, mainEntity)[0]
        # Replace all entities by the new one
        newEntityFacts=Graph()
        for (s,p,o) in entityFacts:
            newEntityFacts.add((yagoClass if s==mainEntity else s, p, o))
        return newEntityFacts
    if mainEntity in yagoTaxonomyUp:
        entityFacts.add((mainEntity,Prefixes.rdfType,Prefixes.rdfsClass))
        for t in entityFacts.triplesWithPredicate(Prefixes.wikidataType):
            entityFacts.remove(t)
    return entityFacts
    
def cleanClasses(entityFacts):
    """Replace all facts <subject, wikidata:type, wikidataClass> by <subject, rdf:type, yagoClass>"""
    for s,p,o in entityFacts.triplesWithPredicate(Prefixes.wikidataType):
        if o in nonYagoClasses:
            entityFacts.add((s,Prefixes.rdfType,nonYagoClasses[o]))
        if o in yagoTaxonomyUp:
            entityFacts.add((s,Prefixes.rdfType,o))
        if any(yagoSchema.subjects(Prefixes.fromClass, o)):
            entityFacts.add((s,Prefixes.rdfType,yagoSchema.subjects(Prefixes.fromClass, o)[0]))
    for t in entityFacts.triplesWithPredicate(Prefixes.wikidataType):
        entityFacts.remove(t)
    return any(entityFacts.triplesWithPredicate(Prefixes.rdfType))

def wikidataPredicate2YagoPredicate(p):
    """Translates a Wikidata predicate to a YAGO predicate -- or None"""
    # Try directly via sh:path
    if any(yagoSchema.subjects(Prefixes.shaclPath, p)) :
        return p    
    # Try via ys:fromProperty
    for b in yagoSchema.subjects(Prefixes.fromProperty, p):
        for s in yagoSchema.objects(b, Prefixes.shaclPath):
            return s
    return None

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
# wd:Q31 p:P1082 s:Q31-93ba9638-404b-66ac-2733-e6292666a326 .
# s:Q31-93ba9638-404b-66ac-2733-e6292666a326 a wikibase:Statement ;
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
    # Find all meta statements about (s, p, _)
    for statement in entityGraph.objects(s, pStatement):
        # If the meta-statement concerns indeed the object o...
        if (statement, pValue, o) in entityGraph:
            # If there is a "duringTime" (pq:P585), return that one
            for duringTime in entityGraph.objects(statement, Prefixes.wikidataDuring):
                return (duringTime, duringTime)
            # Otherwise extract start time and end time
            return(getFirst(entityGraph.objects(statement, Prefixes.wikidataStart)), getFirst(entityGraph.objects(statement, Prefixes.wikidataEnd)))
    return (None, None)

##########################################################################
#             Taxonomy checks
##########################################################################

def getSuperClasses(cls, classes):
    """Adds all superclasses of a class <cls> (including <cls>) to the set <classes>"""
    classes.add(cls)
    # Make a check before because it's a defaultdict,
    # which would create cls if it's not there
    if cls in yagoTaxonomyUp:
        for sc in yagoTaxonomyUp[cls]:
            getSuperClasses(sc, classes)

def anyDisjoint(classes):
    """True if the set <classes> contains any classes that are declared disjoint"""
    return any( (c1 in classes) and (c2 in classes) for (c1, c2) in disjointClasses )        

def getClasses(entityFacts):
    """Returns the set of all classes and their superclasses that the subject is an instance of"""
    classes=set()
    for directClass in entityFacts.objects(None, Prefixes.rdfType):
        getSuperClasses(directClass, classes)        
    return classes

##########################################################################
#             Cardinality checks
##########################################################################

# We use SHACL to specify cardinality checks
#
# A constraint reads like:
# 
# schema:Person sh:property yago-shape-prop:schema-Person-schema-birthDate
# 
# yago-shape-prop:schema-Person-schema-birthDate
#   sh:maxCount  "1"^^xsd:integer

def checkCardinalityConstraints(p, entityFacts):
    """Removes from <entityFacts> any facts with predicate <p> that violate the maxCount property"""
    yagoPredicate=wikidataPredicate2YagoPredicate(p)
    if not yagoPredicate:
        return
    propertyNode = getFirst(yagoSchema.subjects(Prefixes.shaclPath, yagoPredicate))
    if not propertyNode:
        return
    maxCount = getFirst(yagoSchema.objects(propertyNode, Prefixes.shaclMaxCount))
    if not maxCount:
        return
    _, intMaxCount, _, _ = TurtleUtils.splitLiteral(maxCount)    
    if intMaxCount is None or intMaxCount<=0:
        raise Exception("Maxcount has to be a positive int, not "+maxCount)
    for s in entityFacts.subjects():
        if len(set(entityFacts.objects(s, p)))>intMaxCount:
            for o in entityFacts.objects(s,p):
                entityFacts.remove((s, p, o))        
    
        
##########################################################################
#             Domain and range checks
##########################################################################

# We use SHACL to specify domain and range checks
#
# A constraint reads like:
# 
# schema:Person sh:property yago-shape-prop:schema-Person-schema-birthDate
# 
# yago-shape-prop:schema-Person-schema-birthDate
#   sh:path  schema:birthDate,
#   sh:maxCount  "1"^^xsd:integer
#   sh:node <targetClass> 
#   sh:datatype  xsd:string
#   sh:pattern  <regex>

def checkDomain(p, classes):
    """True if the domain of predicate <p> appears in the set <classes>"""
    for c in classes:        
        for propertyNode in yagoSchema.objects(c, Prefixes.shaclProperty):
            if (propertyNode, Prefixes.shaclPath, p) in yagoSchema:
                return True
    return False    

def checkDatatype(datatype, o):
    """True if the object <o> conforms to the <datatype>"""
    if datatype==Prefixes.xsdAnyURI:
        return not o.startswith('"')
    literalValue, _, lang, literalDataType = TurtleUtils.splitLiteral(o)
    if literalValue is None:
        return False
    if datatype==Prefixes.xsdString:
        return literalDataType is None
    if datatype==Prefixes.rdfLangString:
        return literalDataType is None and lang is not None
    return literalDataType==datatype        
        
def checkRangePropertyNode(propertyNode, o):
    """True if the object <o> conforms to the range constraints given by the yago-shape-prop node <propertNode>. False if it does not. Otherwise, returns a list of permissible types."""
    # Disjunctions
    disjunctObject = getFirst(yagoSchema.objects(propertyNode, Prefixes.shaclOr))
    if disjunctObject:
        possiblePropertyNodes = yagoSchema.getList(disjunctObject)
        resultList=[]
        for possiblePropertyNode in possiblePropertyNodes:
            result=checkRangePropertyNode(possiblePropertyNode, o)
            if result==True:
               return True
            if result==False:
                continue
            resultList.append(result)
        if len(resultList)==0:
            return False
        return resultList
        
    # Patterns are verified in a fall-through fashion,
    # because verifying a pattern is a necessary but not sufficient condition
    patternObject = getFirst(yagoSchema.objects(propertyNode, Prefixes.shaclPattern))
    if patternObject:
       objectValue=TurtleUtils.splitLiteral(o)[0]
       if objectValue is None:
           return False       
       patternString=TurtleUtils.splitLiteral(patternObject)[0]
       if patternString is None:
            raise Exception("SHACL pattern has to be a string: "+str(propertyNode)+" "+str(patternObject))
       if not re.match(patternString, objectValue):
           return False
    
    # Datatypes
    datatype = getFirst(yagoSchema.objects(propertyNode, Prefixes.shaclDatatype))
    if datatype:
       return checkDatatype(datatype, o)
    
    # Classes
    rangeClass = getFirst(yagoSchema.objects(propertyNode, Prefixes.shaclNode))
    if rangeClass:       
        return [ rangeClass ]
    
    # If no type can be established, we fail
    return False
    
def checkRange(p, o):
    """True if the object <o> conforms to the range constraint of predicate <p>. False if it does not. Otherwise, returns a list of classes that <o> would have to belong to."""
    # ASSUMPTION: the object types for the predicate p are the same, no matter the subject type
    propertyNode = getFirst(yagoSchema.subjects(Prefixes.shaclPath, p))
    if not propertyNode:
        return False
    return checkRangePropertyNode(propertyNode, o)
    
##########################################################################
#             Main method
##########################################################################

with TsvUtils.TsvFileWriter(FOLDER+"03-yago-facts-to-type-check.tsv") as yagoFacts:
    for entityFacts in TurtleUtils.readWikidataEntities(WIKIDATA_FILE):         
        
        # Anything that is rdf:type in Wikidata is meta-statements, 
        # and should go away
        for t in entityFacts.triplesWithPredicate(Prefixes.rdfType):
            entityFacts.remove(t)
                   
        cleanArticles(entityFacts)               
        
        entityFacts=checkIfClass(entityFacts)
        
        if not cleanClasses(entityFacts):
            continue
             
        classes = getClasses(entityFacts)
        if anyDisjoint(classes):
            continue

        for p in entityFacts.predicates():
            checkCardinalityConstraints(p, entityFacts)

        for s,p,o in entityFacts:
            if p==Prefixes.rdfType:
                yagoFacts.writeFact(s,"rdf:type",o)
                continue
            else:
                yagoPredicate = wikidataPredicate2YagoPredicate(p)
            if not yagoPredicate:
                continue
            if not checkDomain(yagoPredicate, classes):
                continue
            rangeResult=checkRange(yagoPredicate, o)
            if rangeResult is False:
                continue            
            (startDate, endDate) = getStartAndEndDate(s, p, o, entityFacts)
            if rangeResult is True:
                yagoFacts.write(s,yagoPredicate,o, ". #", "", startDate, endDate)
            else:
                yagoFacts.write(s,yagoPredicate,o,". # IF",(", ".join(rangeResult)), startDate, endDate)           

print("done")

if TEST:
    evaluator.compare(FOLDER+"03-yago-facts-to-type-check.tsv")