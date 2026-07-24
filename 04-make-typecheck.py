"""
Typechecks the facts of YAGO

CC-BY 2022-2025 Fabian M. Suchanek

Call:
  python3 make-typecheck.py

Input:
- 01-yago-schema.ttl
- 02-yago-taxonomy-to-rename.tsv
- 03-yago-facts-to-type-check.tsv

Output:
- 04-yago-facts-to-rename.tsv (type checked YAGO facts without correct ids)
- 04-yago-ids.tsv (maps Wikidata ids to YAGO ids)
- 04-yago-bad-classes.tsv (lists classes that don't have instances)

Algorithm:
- run through all facts of yago-facts-to-type-check.tsv, 
  load classes and instances
- run through all facts in yago-facts-to-type-check.tsv, do type check
    - write out facts that fulfill the constraints to yago-facts-to-rename.tsv
    - if there are any such facts, write out the id to yago-ids.tsv
   
"""

##########################################################################
#             Booting
##########################################################################

import sys
from urllib import parse
import TsvUtils
import TurtleUtils
import re
import unicodedata
import Evaluator
import Prefixes
from Schema import YagoSchema
from TurtleUtils import Graph
from collections import defaultdict

TEST=len(sys.argv)>1 and sys.argv[1]=="--test"
FOLDER="test-data/04-make-typecheck/" if TEST else "yago-data/"
SCHEMA_FILE = "yago-data/01-yago-schema.ttl"

def getFirst(iterable, default=None):
    """ Returns the first element of an iterable or None"""
    if iterable is None:
        return None
    return next(iter(iterable), default)
     
##########################################################################
#             YAGO ids
##########################################################################

# Keeps all YAGO titles (= id minus the prefix) to make sure we do not have duplicates
yagoTitles=set()

def hexCode(char):    
    """ Hex-encodes the character """
    return "_U{0:04X}_".format(ord(char))

def inRange(char,start,end):
    """ TRUE if the ordinal of the character is in the range of numbers"""
    return ord(char)>=start and ord(char)<=end
        
def legal(char):
    """ TRUE if a character is a valid CURIE character.
    We're very restrictive here to make all parsers work.
    For example, percentage codes are legal characters in the specification,
    but don't work in Hermit. 
    The accepted characters are PN_CHARS_U | '-' | [0-9]  -- without ranges above 0x0FFF
    """
    return char=='_' or char=='-' or inRange(char, ord('0'), ord('9')) or inRange(char, ord('A'), ord('Z')) or inRange(char, ord('a'), ord('z')) or inRange(char, 0x00C0, 0x00D6) or inRange(char, 0x00D8, 0x00F6) or inRange(char, 0x00F8, 0x02FF) or inRange(char, 0x0370, 0x037D)

def allLegal(s):
    """ True if all characters are legal characters """
    return all(c==' ' or legal(c) for c in s)

def titleFromName(s):
    """ Creates a YAGO title from a name, mirroring every character """
    result=Prefixes.namePrefix
    for c in s:
        if legal(c):
            result+=c
        else:
            result+=hexCode(c)
    return result
    
def titleFromString(s):
    """ Creates a YAGO title from a string """
    result=""
    for c in s:
        if legal(c):
            result+=c
        elif ord(c)<0x009F: # Punctuation becomes underscore
            result+='_'
        else: # Other letters become hyphen
            result+="-"
    # Compress subsequent underscores
    result=re.sub("_+","_",result)
    # Remove trailing underscore
    if result.endswith("_"):
        result=result[0:-1]
    # Remove starting underscore
    if result.startswith("_"):
        result=result[1:]        
    # Special case that is disallowed
    if result.startswith("-"):
        result="Y"+result
    # Special case for Hermit parser
    result=result.replace("genid","gen_id")
    return result
 
def titleFromWikipediaPage(wikipediaPageTitle):
    """ Creates a YAGO id from a Wikipedia page title"""
    return titleFromString(parse.unquote(wikipediaPageTitle))
    
def titleFromLabel(wikidataEntity,label):
    """ Creates a YAGO id from label -- attaching the Wikidata id to avoid ambiguity"""
    yid=titleFromString(label).title()
    if isGoodYagoTitle(yid):
        return yid+"_"+wikidataEntity[3:]
    return None

def titleFromWikidataId(wikidataEntity):
    """ Creates a YAGO id from a Wikidata entity """
    return wikidataEntity[3:]

def isGoodYagoTitle(identifier):
    """ TRUE if the string is long enough"""
    return identifier and len(re.sub("[_-]+","",identifier))>1

def registerTitle(identifier):
    """ Registers YAGO id, returns TRUE on success"""
    if identifier in yagoTitles:
        return False
    yagoTitles.add(identifier)
    return True

def tryYagoId(out,currentTopic, title, isWikipedia=False):
    """ Registers and writes out YAGO id, returns TRUE on success"""
    if not isGoodYagoTitle(title):
        return False
    if registerTitle(title):
        out.write(currentTopic,"owl:sameAs","yago:"+title,". #WIKI" if isWikipedia else ". #OTHER")    
        return True
    return False
    
def writeId(entityGraph, out, isName):
    """ Writes wd:Q303 owl:sameAs yago:Elvis """ 
    subject=entityGraph.mainSubject()
    # Don't print ids for built-in classes
    if subject.startswith("schema:") or subject.startswith("yago:"):
        return
    # Names get an id that mirrors its label
    if isName:
       label=entityGraph.objectWhere(subject, Prefixes.rdfsLabel, lambda s: s.endswith("@mul"))
       if label:          
           out.write(subject,"owl:sameAs", "yago:"+titleFromName(label[1:-5]),". #OTHER") 
           return
    # Try English Wikipedia first
    label=entityGraph.objectWhere(subject, Prefixes.schemaUrl, lambda s: s.startswith('"https://en.wikipedia.org/wiki/'))
    if label and tryYagoId(out,subject, titleFromWikipediaPage(label[30:-13]), True):
        return
    # Next try the English label 
    label=entityGraph.objectWhere(subject, Prefixes.rdfsLabel, lambda s: s.endswith("@en")) 
    if label and tryYagoId(out,subject, titleFromLabel(subject,label[1:-4])):
        return        
    # Try any legible label
    for label in entityGraph.objectsOf(subject, Prefixes.rdfsLabel):
        label=TurtleUtils.splitLiteral(label)[0]
        if tryYagoId(out,subject, titleFromLabel(subject,label)):
            return        
    # Otherwise write the Wikidata ID
    out.write(subject,"owl:sameAs","yago:"+titleFromWikidataId(subject),". #OTHER")

##########################################################################
#             Class operations
##########################################################################

# We register here to which classes an instance belongs
yagoInstances=defaultdict(set)

def createGenericInstance(targetClass, outFile):
    """ Creates a generic instance for a target class, registers the class in classesWithGenericInstances, and writes the instance facts to outFile """
    objectName="_:"+targetClass+"_generic_instance"
    if objectName not in yagoInstances:
        yagoInstances[objectName].add(targetClass)
        outFile.write(objectName, Prefixes.rdfType, targetClass, ".")        
    return(objectName)

# We store the global taxonomy here
yagoTaxonomyUp={}

def isSubClassOfAny_(c, superclasses, seenClasses):
    """ True if this class is a subclass of any of the given superclasses, avoiding loops"""
    if c in seenClasses:
        return False
    if c in superclasses:
        return True
    if c not in yagoTaxonomyUp:
        return False
    seenClasses.add(c)
    for superclass in yagoTaxonomyUp[c]:
        if isSubClassOfAny_(superclass, superclasses, seenClasses):
            return True
    seenClasses.discard(c)
    return False

def isSubClassOfAny(c, superclasses):
    """ True if this class is a subclass of any of the given superclasses"""
    # Can't use default argument as this is instantiated only once
    return isSubClassOfAny_(c, superclasses, set()) 

def isInstanceOfAny(obj, classes):
    """ True if this instance is an instance of any of the given classes"""
    # URIs are instances of anyURI and Thing (for external entities)
    if obj.startswith('<'):
        return Prefixes.xsdAnyURI in classes or Prefixes.schemaThing in classes
    # Literals
    if obj.startswith('"'):
        # These types have been checked beforehand in Step 3
        if any(c.startswith("xsd:") or c.startswith("rdf:") or c.startswith("geo:") or c.startswith("xsd:") for c in classes):
            return True
        # YAGO units are to be checked here    
        elif any(c.startswith(Prefixes.yagoUnit) for c in classes):
            literalValue, _, _, datatype = TurtleUtils.splitLiteral(obj)
            obj = datatype
        # Everything else fails...    
        else:
            return False
    return any(isSubClassOfAny(c, classes) for c in yagoInstances[obj])

def schemaClass(e):
    """ Returns a schema class of which e is an instance """
    if e.startswith('"'):
        literalValue, _, _, datatype = TurtleUtils.splitLiteral(e)
        e = datatype
    c = getFirst(yagoInstances.get(e, [None]))
    while c and not c.startswith("schema:") and not c.startswith("yago:") and not c.startswith("rdf:") and not c.startswith("rdfs:") and not c.startswith("xsd:"):
        c = getFirst(yagoTaxonomyUp.get(c, [None]))
    return c
    
def removeClass(c):
    """ Removes this class and all superclasses from the YAGO taxonomy """    
    # Happens for schema:Thing and rdfs:Class,
    # and in case we already passed by
    if c not in yagoTaxonomyUp:
        return
    for superClass in yagoTaxonomyUp[c]:
        removeClass(superClass)
    yagoTaxonomyUp.pop(c)

# We store the global YAGO Schema here
yagoSchema = None

##########################################################################
#             Main
##########################################################################

def writeFacts(entityGraph, out, idsFile, logFile):
    """ Type checks the facts of the entity and writes them out """
    subject=entityGraph.mainSubject()
            
    # Count how often each object appears
    # We do this to decide when we write a range violation to the log file
    count=0
    objects2freq={}
    for predicate in entityGraph.predicatesOf(subject):
        for obj in entityGraph.objectsOf(subject, predicate):    
            if obj not in objects2freq:
                objects2freq[obj]=0
            objects2freq[obj]+=1
            
    # Write out the facts
    for predicate in entityGraph.predicatesOf(subject):
        yagoProperty=yagoSchema.properties.get(predicate,None)
        targetClasses=yagoProperty.objectTypes if yagoProperty else None
        for obj in entityGraph.objectsOf(subject, predicate):    
            # If the object is a name, we have to discard the fact,
            # because names are removed from the set of entities
            if isInstanceOfAny(obj,[Prefixes.yagoPersonName]):
                continue
            startDate = entityGraph.getMetaFacts((subject, predicate, obj)).get("startDate","")
            endDate = entityGraph.getMetaFacts((subject, predicate, obj)).get("endDate","")
            if predicate==Prefixes.rdfType or not targetClasses or isInstanceOfAny(obj,targetClasses):
                out.write(subject, predicate, obj, ". #", startDate, endDate)
                count+=1
                continue
            if isSubClassOfAny(obj,targetClasses):
                newObject=createGenericInstance(obj, out)
                out.write(subject, predicate, newObject, ". #", startDate, endDate)
                count+=1                    
                continue
            if objects2freq[obj]==1:
                for p in entityGraph.predicatesOf(subject):
                    if obj in entityGraph.objectsOf(subject, p):
                        if schemaClass(obj):
                            logFile.writeMetaFact(subject, p, obj, Prefixes.ysReason, f'"Range check failed: Object is {schemaClass(obj)} and not {' or '.join(str(s) for s in targetClasses)}"')
                        else:
                            logFile.writeMetaFact(subject, p, obj, Prefixes.ysReason, f'"Object not in YAGO"')
            objects2freq[obj]-=1
    return count

with TsvUtils.Timer("Step 04: Type-checking YAGO"):
    # Load schema to register ids of existing classes and properties
    yagoSchema = YagoSchema(SCHEMA_FILE, False)
    for cls in yagoSchema.classes:
        yagoTitles.add(cls[cls.find(':')+1:])
    for prop in yagoSchema.properties:
        yagoTitles.add(prop[prop.find(':')+1:])
        
    # Load taxonomy
    for triple in TsvUtils.tsvTuples(FOLDER+"02-yago-taxonomy-to-rename.tsv", "  Loading YAGO taxonomy"):
        if len(triple)>2:
            if triple[0] not in yagoTaxonomyUp:
                yagoTaxonomyUp[triple[0]]=set()
            yagoTaxonomyUp[triple[0]].add(triple[2])

    # Load instances
    for triple in TsvUtils.tsvTuples(FOLDER+"03-yago-facts-to-type-check.tsv", "  Loading YAGO instances"):
        if len(triple)>2 and triple[1]==Prefixes.rdfType:
            yagoInstances[triple[0]].add(triple[2])
    
    count=0
    with TsvUtils.TsvFileWriter(FOLDER+"04-yago-facts-to-rename.tsv") as out:
        with TsvUtils.TsvFileWriter(FOLDER+"04-yago-ids.tsv") as idsFile:
            with TsvUtils.TsvFileWriter(FOLDER+"04-make-type-check.log") as logFile:
                entityGraph=Graph()                
                
                for split in TsvUtils.tsvTuples(FOLDER+"03-yago-facts-to-type-check.tsv", "  Type-checking facts"):
                    if len(split)<3:
                        continue
                    subject = split[0]    
                    predicate = split[1]
                    obj = split[2]
                    startDate=split[4] if len(split)>4 else ""
                    endDate=split[5] if len(split)>5 else ""                    
                    
                    if len(entityGraph) and subject!=entityGraph.mainSubject():                          
                        isName=isInstanceOfAny(entityGraph.mainSubject(),[Prefixes.yagoPersonName])
                        writeId(entityGraph, idsFile, isName)
                        # For names, we do not write out any facts, and we remove ourselves from the type hierarchy
                        # so that the subclasses of PersonName become empty
                        if isName:
                            yagoInstances.pop(entityGraph.mainSubject(), None)
                        else:    
                            count+=writeFacts(entityGraph, out, idsFile, logFile)
                        entityGraph.clear()
                    entityGraph.add((subject, predicate, obj))
                    if startDate:
                       entityGraph.addMetaFact((subject, predicate, obj),"startDate",startDate)
                    if endDate:
                       entityGraph.addMetaFact((subject, predicate, obj),"endDate",endDate)
                        
                # Also flush the ids of the last entity...
                writeId(entityGraph, idsFile, isName)
                count+=writeFacts(entityGraph, out, idsFile, logFile)

    print("  Info: Number of facts:",count)    
    # Write out classes that did not get any instances    
    for c in set([k for s in yagoInstances.values() for k in s]):
        removeClass(c)     
    print("  Info: Number of classes that don't have instances:",len(yagoTaxonomyUp))
    with TsvUtils.TsvFileWriter(FOLDER+"04-yago-bad-classes.tsv") as badClassFile:
        for c in yagoTaxonomyUp:
            badClassFile.write(c)

if TEST:
    Evaluator.compare(FOLDER+"04-yago-facts-to-rename.tsv")
    Evaluator.compare(FOLDER+"04-yago-ids.tsv")
    Evaluator.compare(FOLDER+"04-yago-bad-classes.tsv")