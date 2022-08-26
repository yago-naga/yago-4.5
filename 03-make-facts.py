"""
Creates the the YAGO facts from the Wikidata facts

(c) 2022 Fabian M. Suchanek

Call:
  python3 make-facts.py

Input:
- 01-yago-taxonomy.tsv
- 01-yago-schema.ttl
- 01-non-yago-classes.tsv
- Wikidata file in input-data/wikidata.ttl.gz

Output:
- 02-yago-facts-to-type-check.tsv

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
FOLDER="test-data/02-make-facts/" if TEST else "yago-data/"
WIKIDATA_FILE= "test-data/02-make-facts/00-wikidata.ttl" if TEST else "input-data/wikidata.ttl.gz"

##########################################################################
#             Booting
##########################################################################

print("Creating YAGO facts...")
print("  Importing...",end="", flush=True)
# Importing alone takes so much time that a status message is in order...
from rdflib import URIRef, RDFS, RDF, OWL, Graph, Literal, XSD, collection
import utils
import sys
import re
import evaluator
from collections import defaultdict
print("done")

print("  Loading YAGO schema...", end="", flush=True)
yagoSchema=Graph()
yagoSchema.parse(FOLDER+"01-yago-schema.ttl", format="turtle")
disjointClasses=[ (utils.compressPrefix(c1), utils.compressPrefix(c2)) for (c1, p, c2) in yagoSchema.triples((None, OWL.disjointWith, None)) ]
print("done")

yagoTaxonomyUp=defaultdict(set)
for triple in utils.readTsvTuples(FOLDER+"01-yago-taxonomy.tsv", "  Loading YAGO taxonomy"):
    if len(triple)>3:
        yagoTaxonomyUp[triple[0]].add(triple[2])

nonYagoClasses={}
for triple in utils.readTsvTuples(FOLDER+"01-non-yago-classes.tsv", "  Loading non-YAGO classes"):
    if len(triple)>3:
        nonYagoClasses[triple[0]]=utils.expandPrefix(triple[2])

##########################################################################
#             Cleaning of entities
##########################################################################

def cleanArticles(entityFacts):
    """ Changes <page, schema:about, entity> to <entity, mainentityOfPage, page> """
    entityAndPage=[ (s, o) for s, p, o in entityFacts.triples((None, utils.schemaAbout, None))]
    entityFacts.remove((None, utils.schemaAbout, None))
    for (s, o) in entityAndPage:
        entityFacts.add((o, URIRef("https://schema.org/mainEntityOfPage"), s))
                
def checkIfClass(entityFacts):
    """Adds <subject, rdf:type, rdfs:Class> if this is a class. Removes all other type relationships."""
    for s in entityFacts.subjects(RDFS.label, None):
        if utils.compressPrefix(s) in yagoTaxonomyUp:
            entityFacts.add((s,RDF.type,RDFS.Class))
    if (None,RDF.type,RDFS.Class) in entityFacts:
        entityFacts.remove((None, utils.wikidataType, None))    

def cleanClasses(entityFacts):
    """Replace all facts <subject, wikidata:type, wikidataClass> by <subject, rdf:type, yagoClass>"""
    for s,p,o in entityFacts.triples((None, utils.wikidataType, None)):
        compressedO=utils.compressPrefix(o)
        if compressedO in nonYagoClasses:
            entityFacts.add((s,RDF.type,nonYagoClasses[compressedO]))
        if compressedO in yagoTaxonomyUp:
            entityFacts.add((s,RDF.type,o))
    entityFacts.remove((None, utils.wikidataType, None))    
    return (None, RDF.type, None) in entityFacts

def wikidataPredicate2YagoPredicate(p):
    """Translates a Wikidata predicate to a YAGO predicate -- or None"""
    # Try directly via sh:path
    if (None, utils.shaclPath, p) in yagoSchema:
        return p    
    # Try via ys:fromProperty
    for b in yagoSchema.subjects(utils.fromProperty, p):
        for s in yagoSchema.objects(b, utils.shaclPath):
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
    """ Returns a tuple of a start date and an end date for this fact. Unknown components are None. """
    # The property should be in the namespace WDT
    if not p.startswith("http://www.wikidata.org/prop/direct/"):
        return (None, None)
    # Translate to the namespace P
    pStatement=URIRef("http://www.wikidata.org/prop/"+p[36:])
    # Translate to the namespace PS
    pValue=URIRef("http://www.wikidata.org/prop/statement/"+p[36:])
    # Find all meta statements about (s, p, _)
    for statement in entityGraph.objects(s, pStatement):
        # If the meta-statement concerns indeed the object o...
        if (statement, pValue, o) in entityGraph:
            # If there is a "duringTime" (pq:P585), return that one
            for duringTime in entityGraph.objects(statement, utils.wikidataDuring):
                return (duringTime, duringTime)
            # Otherwise extract start time and end time
            return(next(entityGraph.objects(statement, utils.wikidataStart), None), next(entityGraph.objects(statement, utils.wikidataEnd), None))
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
    for directClass in entityFacts.objects(None, RDF.type):
        getSuperClasses(utils.compressPrefix(directClass), classes)        
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
    propertyNode = next(yagoSchema.subjects(utils.shaclPath, yagoPredicate), None)
    if not propertyNode:
        return
    maxCount = next(yagoSchema.objects(propertyNode, utils.shaclMaxCount), None)
    if not maxCount:
        return
    if not isinstance(maxCount, Literal) or int(maxCount.value)<=0:
        raise Exception("Maxcount has to be a positive int, not "+maxCount)
    if len(set(entityFacts.objects(None, p)))>int(maxCount.value):
        entityFacts.remove((None, p, None))        
    
        
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
        for propertyNode in yagoSchema.objects(utils.expandPrefix(c), utils.shaclProperty):
            if (propertyNode, utils.shaclPath, p) in yagoSchema:
                return True
    return False    

def checkDatatype(datatype, o):
    """True if the object <o> conforms to the <datatype>"""
    #print("  Checking if "+str(o)+" has datatype "+str(datatype))
    if datatype==XSD.anyURI:
        return isinstance(o,URIRef)
    if not isinstance(o, Literal):
        #print("  "+str(o)+" is not a literal")
        return False
    if datatype==XSD.string:
        return o.datatype is None
    if datatype==RDF.langString:
        return o.datatype is None and o.language is not None
    return datatype==o.datatype        
        
def checkRangePropertyNode(propertyNode, o):
    """True if the object <o> conforms to the range constraints given by the yago-shape-prop node <propertNode>. False if it does not. Otherwise, returns a list of permissible types."""
    # Disjunctions
    disjunctObject = next(yagoSchema.objects(propertyNode, utils.shaclOr), None)
    if disjunctObject:
        possiblePropertyNodes = collection.Collection(yagoSchema, disjunctObject)
        #print("   is disjunction: "+str(possiblePropertyNodes))
        resultList=[]
        for possiblePropertyNode in possiblePropertyNodes:
            result=checkRangePropertyNode(possiblePropertyNode, o)
            #print("    checking: "+str(result))
            if result==True:
               return True
            if result==False:
                continue
            resultList=resultList+result
        #print("   disjunction result: "+str(resultList))
        if len(resultList)==0:
            return False
        return resultList
        
    # Patterns are verified in a fall-through fashion,
    # because verifying a pattern is a necessary but not sufficient condition
    patternObject = next(yagoSchema.objects(propertyNode, utils.shaclPattern), None)
    if patternObject: 
       if not isinstance(o, Literal):
           #print("  Pattern "+str(patternObject)+" cannot match because object is not a string: "+str(o))
           return False
       string = o.value    
       if not isinstance(patternObject, Literal):
            raise Exception("SHACL pattern has to be a string: "+str(propertyNode)+" "+str(patternObject))
       patternString = patternObject.value    
       if not re.match(patternString, string):
           #print("  Pattern "+patternString+" does not match: "+string)
           return False
    
    # Datatypes
    datatype = next(yagoSchema.objects(propertyNode, utils.shaclDatatype), None)
    if datatype:
       return checkDatatype(datatype, o)
    
    # Classes
    rangeClass = next(yagoSchema.objects(propertyNode, utils.shaclNode), None)
    if rangeClass:       
        return [ utils.compressPrefix(rangeClass) ]
    
    # If no type can be established, we fail
    return False
    
def checkRange(p, o):
    """True if the object <o> conforms to the range constraint of predicate <p>. False if it does not. Otherwise, returns a list of classes that <o> would have to belong to."""
    # ASSUMPTION: the object types for the predicate p are the same, no matter the subject type
    propertyNode = next(yagoSchema.subjects(utils.shaclPath, p), None)
    #print("  Range check for "+str(p)+" "+str(o)+" with prop node "+str(propertyNode))
    if not propertyNode:
        return False
    return checkRangePropertyNode(propertyNode, o)
    
##########################################################################
#             Main method
##########################################################################

with utils.TsvFileWriter(FOLDER+"02-yago-facts-to-type-check.tsv") as yagoFacts:
    for entityFacts in utils.readWikidataEntities(WIKIDATA_FILE):         
        # Anything that is rdf:type in Wikidata is meta-statements, 
        # and should go away
        entityFacts.remove((None, RDF.type, None))    
        cleanArticles(entityFacts)
        
        checkIfClass(entityFacts)
        if not cleanClasses(entityFacts):
            continue
        classes = getClasses(entityFacts)
        if anyDisjoint(classes):
            continue
        for p in set(entityFacts.predicates()):
            checkCardinalityConstraints(p, entityFacts)
        
        for s,p,o in entityFacts:
            #print(" Predicate: "+str(p))
            if p==RDF.type:
                yagoFacts.writeFact(utils.compressPrefix(s),"rdf:type",utils.compressPrefix(o))
                continue
            else:
                yagoPredicate = wikidataPredicate2YagoPredicate(p)
            #print(" in YAGO: "+str(yagoPredicate))
            if not yagoPredicate:
                continue
            if not checkDomain(yagoPredicate, classes):
                #print(" domain check failed")
                continue
            rangeResult=checkRange(yagoPredicate, o)
            if rangeResult is False:
                #print(" range check failed")
                continue
            (startDate, endDate) = getStartAndEndDate(s, p, o, entityFacts)
            if rangeResult is True:
                yagoFacts.write(utils.compressPrefix(s),utils.compressPrefix(yagoPredicate),utils.compressPrefix(o), ".", "", utils.compressPrefix(startDate), utils.compressPrefix(endDate))
            else:
                #print(str(rangeResult))
                yagoFacts.write(utils.compressPrefix(s),utils.compressPrefix(yagoPredicate),utils.compressPrefix(o),". # IF",(", ".join(rangeResult)), utils.compressPrefix(startDate), utils.compressPrefix(endDate))           

print("done")

if TEST:
    evaluator.compare(FOLDER+"02-yago-facts-to-type-check.tsv")