"""
Creates the the YAGO facts from the Wikidata facts

(c) 2022 Fabian M. Suchanek

Call:
  python3 make-facts.py

Input:
- yago-taxonomy.tsv
- yago-schema.ttl
- non-yago-classes.tsv
- Wikidata file in input-data/wikidata.ttl.gz

Output:
- yago-facts-to-type-check.tsv

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
WIKIDATA_FILE= "test-data/02-make-facts/wikidata.ttl" if TEST else "input-data/wikidata.ttl.gz"

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
print("done")

print("  Loading YAGO taxonomy...", end="", flush=True)
yagoTaxonomy=Graph()
yagoTaxonomy.parse(FOLDER+"yago-taxonomy.tsv", format="turtle")
yagoTaxonomy.parse(FOLDER+"yago-schema.ttl", format="turtle")
print("done")

print("  Loading non-YAGO classes...", end="", flush=True)
unmappedClasses=Graph()
unmappedClasses.parse(FOLDER+"non-yago-classes.tsv", format="turtle")
print("done")

##########################################################################
#             Cleaning of entities
##########################################################################

def cleanClasses(entityFacts):
    """Replace all facts <subject, wikidata:type, wikidataClass> by <subject, rdf:type, yagoClass>"""
    for s,p,o in entityFacts.triples((None, utils.wikidataType, None)):
        for targetClass in unmappedClasses.objects(o, RDFS.subClassOf):
            entityFacts.add((s,RDF.type,targetClass))
        if (o, RDFS.subClassOf,None) in yagoTaxonomy:
            entityFacts.add((s,RDF.type,o))
    entityFacts.remove((None, utils.wikidataType, None))    
    return (None, RDF.type, None) in entityFacts

def wikidataPredicate2YagoPredicate(p):
    """Translates a Wikidata predicate to a YAGO predicate -- or None"""
    for b in yagoTaxonomy.subjects(utils.fromProperty, p):
        for s in yagoTaxonomy.objects(b, utils.shaclPath):
            return s
    return None
    
##########################################################################
#             Taxonomy checks
##########################################################################

def getSuperClasses(cls, classes):
    """Adds all superclasses of a class <cls> (including <cls>) to the set <classes>"""
    classes.add(cls)
    for sc in yagoTaxonomy.objects(cls, RDFS.subClassOf):
        getSuperClasses(sc, classes)

def anyDisjoint(classes):
    """True if the set <classes> contains any classes that are declared disjoint"""
    return any( (s in classes) and (o in classes) for s,p,o in yagoTaxonomy.triples((None, OWL.disjointWith, None)) )        

def getClasses(entityFacts):
    """Returns the set of all classes and their superclasses that the subject is an instance of"""
    classes=set()
    for directClass in entityFacts.objects(None, RDF.type):
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
    propertyNode = next(yagoTaxonomy.subjects(utils.shaclPath, yagoPredicate), None)
    if not propertyNode:
        return
    maxCount = next(yagoTaxonomy.objects(propertyNode, utils.shaclMaxCount), None)
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
        for propertyNode in yagoTaxonomy.objects(c, utils.shaclProperty):
            if (propertyNode, utils.shaclPath, p) in yagoTaxonomy:
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
    disjunctObject = next(yagoTaxonomy.objects(propertyNode, utils.shaclOr), None)
    if disjunctObject:
        possiblePropertyNodes = collection.Collection(yagoTaxonomy, disjunctObject)
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
    patternObject = next(yagoTaxonomy.objects(propertyNode, utils.shaclPattern), None)
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
    datatype = next(yagoTaxonomy.objects(propertyNode, utils.shaclDatatype), None)
    if datatype:
       return checkDatatype(datatype, o)
    
    # Classes
    rangeClass = next(yagoTaxonomy.objects(propertyNode, utils.shaclNode), None)
    if rangeClass:       
        return [ utils.compress(rangeClass) ]
    
    # If no type can be established, we fail
    return False
    
def checkRange(p, o):
    """True if the object <o> conforms to the range constraint of predicate <p>. False if it does not. Otherwise, returns a list of classes that <o> would have to belong to."""
    # ASSUMPTION: the object types for the predicate p are the same, no matter the subject type
    propertyNode = next(yagoTaxonomy.subjects(utils.shaclPath, p), None)
    #print("  Range check for "+str(p)+" "+str(o)+" with prop node "+str(propertyNode))
    if not propertyNode:
        return False
    return checkRangePropertyNode(propertyNode, o)
    
##########################################################################
#             Main method
##########################################################################

with utils.TsvFile(FOLDER+"yago-facts-to-type-check.tsv") as yagoFacts:
    for entityFacts in utils.readWikidataEntities(WIKIDATA_FILE): 
        #utils.printGraph(entityFacts)
        if not cleanClasses(entityFacts):
            continue
        classes = getClasses(entityFacts)
        if anyDisjoint(classes):
            continue
        for p in set(entityFacts.predicates()):
            checkCardinalityConstraints(p, entityFacts)
        for s,p,o in entityFacts:
            #print(str(s)+" "+str(p)+' '+str(o))
            if p==RDF.type:
                yagoFacts.writeFact(utils.compress(s),"rdf:type",utils.compress(o))
                continue
            if p==utils.schemaAbout:
                yagoPredicate=URIRef("https://schema.org/mainEntityOfPage")
                tmp=s
                s=o
                o=tmp
            else:
                yagoPredicate = wikidataPredicate2YagoPredicate(p)
            #print(" in YAGO: "+str(yagoPredicate))
            if not yagoPredicate:
                continue
            if not checkDomain(yagoPredicate, classes):
                #print(" domain check failed")
                continue
            rangeResult=checkRange(yagoPredicate, o)
            if rangeResult is True:
                yagoFacts.writeFact(utils.compress(s),utils.compress(yagoPredicate),utils.compress(o))
            elif rangeResult is False:
                #print(" range check failed")
                continue
            else:
                #print(str(rangeResult))
                yagoFacts.write(utils.compress(s),utils.compress(yagoPredicate),utils.compress(o),". # IF",(", ".join(rangeResult)))           

print("done")
