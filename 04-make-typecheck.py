"""
Typechecks the facts of YAGO

CC-BY 2022-2025 Fabian M. Suchanek

Call:
  python3 make-typecheck.py

Input:
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
from collections import defaultdict

TEST=len(sys.argv)>1 and sys.argv[1]=="--test"
FOLDER="test-data/04-make-typecheck/" if TEST else "yago-data/"
        
##########################################################################
#             YAGO ids
##########################################################################

# Keeps all YAGO ids to make sure we do not have duplicates
yagoIds=set()

def hexCode(char):    
    """ Hex-encodes the character """
    return "_u{0:04X}_".format(ord(char))

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
    
def yagoIdFromString(s):
    """ Creates a YAGO id from a string """
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
 
def yagoIdFromWikipediaPage(wikipediaPageTitle):
    """ Creates a YAGO id from a Wikipedia page title"""
    return yagoIdFromString(parse.unquote(wikipediaPageTitle))
    
def yagoIdFromLabel(wikidataEntity,label):
    """ Creates a YAGO id from a Wikidata entity and label """
    return yagoIdFromString(label).title()+"_"+wikidataEntity[3:]

def yagoIdFromWikidataId(wikidataEntity):
    """ Creates a YAGO id from a Wikidata entity """
    return wikidataEntity[3:]

def isGoodYagoId(identifier):
    """ TRUE if the string is long enough"""
    return identifier and len(identifier.replace("-","").replace("-",""))>3

def registerYagoId(identifier):
    """ Registers YAGO id, returns TRUE on success"""
    if identifier in yagoIds:
        return False
    yagoIds.add(identifier)
    return True

def tryYagoId(out,currentTopic, yagoId, isWikipedia=False):
    """ Registers and writes out YAGO id, returns TRUE on success"""
    if not isGoodYagoId(yagoId):
        return False
    if registerYagoId(yagoId):
        out.write(currentTopic,"owl:sameAs","yago:"+yagoId,". #WIKI" if isWikipedia else ". #OTHER")
    else:
        out.write(currentTopic,"owl:sameAs","yago:"+yagoId+"_"+currentTopic[3:], ". #WIKI" if isWikipedia else ". #OTHER")
    return True
    
def writeYagoId(out, currentTopic, currentEnglishLabel, currentLabel, currentWikipediaPage):
    """ Writes wd:Q303 owl:sameAs yago:Elvis """ 
    # Don't print ids for built-in classes
    if currentTopic.startswith("schema:") or currentTopic.startswith("yago:"):
        return
    if currentWikipediaPage and tryYagoId(out,currentTopic, yagoIdFromWikipediaPage(currentWikipediaPage), True):
        return
    if currentEnglishLabel and tryYagoId(out,currentTopic, yagoIdFromLabel(currentTopic,currentEnglishLabel)):
        return        
    if currentLabel and tryYagoId(out,currentTopic, yagoIdFromLabel(currentTopic,currentLabel)):
        return        
    out.write(currentTopic,"owl:sameAs","yago:"+yagoIdFromWikidataId(currentTopic),". #OTHER")

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

def isSubclassOf(c1, c2):
    if c1==c2:
        return True
    if c1 not in yagoTaxonomyUp:
        return
    for superclass in yagoTaxonomyUp[c1]:
        if isSubclassOf(superclass, c2):
            return True
    return False
    
def instanceOf(obj, cls):
    return any(isSubclassOf(c, cls) for c in yagoInstances[obj])
    
def removeClass(c):
    """ Removes this class and all superclasses from the YAGO taxonomy """    
    # Happens for schema:Thing and rdfs:Class,
    # and in case we already passed by
    if c not in yagoTaxonomyUp:
        return
    for superClass in yagoTaxonomyUp[c]:
        removeClass(superClass)
    yagoTaxonomyUp.pop(c)

##########################################################################
#             Main
##########################################################################

with TsvUtils.Timer("Step 04: Type-checking YAGO"):
    # Load taxonomy
    for triple in TsvUtils.tsvTuples(FOLDER+"02-yago-taxonomy-to-rename.tsv", "  Loading YAGO taxonomy"):
        if len(triple)>3:
            if triple[0] not in yagoTaxonomyUp:
                yagoTaxonomyUp[triple[0]]=set()
            yagoTaxonomyUp[triple[0]].add(triple[2])

    # Load instances
    for triple in TsvUtils.tsvTuples(FOLDER+"03-yago-facts-to-type-check.tsv", "  Loading YAGO instances"):
        if len(triple)>2 and triple[1]=="rdf:type":
            yagoInstances[triple[0]].add(triple[2])
    
    count=0
    with TsvUtils.TsvFileWriter(FOLDER+"04-yago-facts-to-rename.tsv") as out:
        with TsvUtils.TsvFileWriter(FOLDER+"04-yago-ids.tsv") as idsFile:
            currentTopic=""
            currentEnglishLabel=""
            currentLabel=""
            currentWikipediaPage=""
            wroteFacts=False # True if the entity had any valid facts
            for split in TsvUtils.tsvTuples(FOLDER+"03-yago-facts-to-type-check.tsv", "  Type-checking facts"):
                if len(split)<3:
                    continue
                    
                # Next entity
                if split[0]!=currentTopic:
                    if wroteFacts:
                        writeYagoId(idsFile, currentTopic, currentEnglishLabel, currentLabel, currentWikipediaPage)
                    currentTopic=split[0]
                    currentEnglishLabel=""
                    currentLabel=""
                    currentWikipediaPage=""
                    wroteFacts=False
                    
                # Gather information for the entity id
                if split[1]=="rdfs:label":
                    if split[2].endswith('"@en'):
                        currentEnglishLabel=split[2][1:-4]
                    elif not currentEnglishLabel and not currentLabel:
                        label=TurtleUtils.splitLiteral(split[2])[0]
                        if allLegal(label):
                            currentLabel=label    
                elif split[1]=="schema:mainEntityOfPage" and split[2].startswith('"https://en.wikipedia.org/wiki/'):
                    currentWikipediaPage=split[2][31:-13]
                
                # Write out the fact
                startDate=split[5] if len(split)>5 else ""
                endDate=split[6] if len(split)>6 else ""
                classes=split[4].split(", ") if len(split)>4 and len(split[4])>0 else None
                if classes is None or any(instanceOf(split[2],c) for c in classes):
                    out.write(split[0], split[1], split[2], ". #", startDate, endDate)
                    wroteFacts=True
                    count+=1
                elif any(isSubclassOf(split[2],c) for c in classes):
                    newObject=createGenericInstance(split[2], out)
                    out.write(split[0], split[1], newObject, ". #", startDate, endDate)
                    count+=1
                    wroteFacts=True
                    
            # Also flush the ids of the last entity...
            if wroteFacts:
                writeYagoId(idsFile, currentTopic, currentEnglishLabel, currentLabel, currentWikipediaPage)

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