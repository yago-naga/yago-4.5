"""
Typechecks the facts of YAGO

(c) 2022 Fabian M. Suchanek

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

TEST=False
FOLDER="test-data/04-make-typecheck/" if TEST else "yago-data/"

##########################################################################
#             Booting
##########################################################################

import sys
from urllib import parse
import TsvUtils
import re
import unicodedata
import evaluator
import Prefixes
from collections import defaultdict
        
##########################################################################
#             YAGO ids
##########################################################################

def hexCode(char):    
    """ Hex-encodes the character """
    return "_u{0:04X}_".format(ord(char))
    
def legal(char):
    """ TRUE if a character is a valid CURIE character.
    We're very restrictive here to make all parsers work.
    For example, percentage codes are legal characters in the specification,
    but don't work in Hermit. """
    category=unicodedata.category(char)[0]
    return char in "_-0123456789" or (category=="L" and (ord(char)>=0x00C0  or ord(char)<=ord('z')))
 
def yagoIdFromString(s):
    """ Creates a YAGO id from a string """
    result=""
    for c in s:
        if legal(c):
            result+=c
        elif c==' ':
            result+='_'
        else:
            result+=hexCode(c)
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

# We collect Wikipedia page titles that are already in use
# because some Wikidata entities point to the same Wikipedia page
wikipediaPagesUsed=set()

def writeYagoId(out, currentTopic, currentLabel, currentWikipediaPage):
    """ Writes wd:Q303 owl:sameAs yago:Elvis """ 
    # Don't print ids for built-in classes
    if currentTopic.startswith("schema:"):
        return
    if currentWikipediaPage and currentWikipediaPage not in wikipediaPagesUsed:
        out.write(currentTopic,"owl:sameAs","yago:"+yagoIdFromWikipediaPage(currentWikipediaPage),". #WIKI")
        wikipediaPagesUsed.add(currentWikipediaPage)
        return
    if currentLabel:
        out.write(currentTopic,"owl:sameAs","yago:"+yagoIdFromLabel(currentTopic,currentLabel),". #OTHER")
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
        outFile.write(objectName, Prefixes.rdfsLabel, '"Generic instance"@en', ".")
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
    # and in case we already passd by
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
    for tuple in TsvUtils.tsvTuples(FOLDER+"02-yago-taxonomy-to-rename.tsv", "  Loading YAGO taxonomy"):
        if len(tuple)>3:
            if tuple[0] not in yagoTaxonomyUp:
                yagoTaxonomyUp[tuple[0]]=set()
            yagoTaxonomyUp[tuple[0]].add(tuple[2])

    # Load instances
    for tuple in TsvUtils.tsvTuples(FOLDER+"03-yago-facts-to-type-check.tsv", "  Loading YAGO instances"):
        if len(tuple)>2 and tuple[1]=="rdf:type":
            yagoInstances[tuple[0]].add(tuple[2])
    
    count=0
    with TsvUtils.TsvFileWriter(FOLDER+"04-yago-facts-to-rename.tsv") as out:
        with TsvUtils.TsvFileWriter(FOLDER+"04-yago-ids.tsv") as idsFile:
            currentTopic=""
            currentLabel=""
            currentWikipediaPage=""
            wroteFacts=False # True if the entity had any valid facts
            for split in TsvUtils.tsvTuples(FOLDER+"03-yago-facts-to-type-check.tsv", "  Type-checking facts"):
                if len(split)<3:
                    continue
                    
                # Next entity
                if split[0]!=currentTopic:
                    if wroteFacts:
                        writeYagoId(idsFile, currentTopic, currentLabel, currentWikipediaPage)
                    currentTopic=split[0]
                    currentLabel=""
                    currentWikipediaPage=""
                    wroteFacts=False
                    
                # Gather information for the entity id
                if split[1]=="rdfs:label" and split[2].endswith('"@en'):
                    currentLabel=split[2][1:-4]
                elif split[1]=="schema:mainEntityOfPage" and split[2].startswith('<https://en.wikipedia.org/wiki/'):
                    currentWikipediaPage=split[2][31:-1]
                
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
                writeYagoId(idsFile, currentTopic, currentLabel, currentWikipediaPage)

    print("  Info: Number of facts:",count)    
    # Write out classes that did not get any instances    
    for c in set([k for s in yagoInstances.values() for k in s]):
        removeClass(c)        
    print("  Info: Number of classes that don't have instances:",len(yagoTaxonomyUp))
    with TsvUtils.TsvFileWriter(FOLDER+"04-yago-bad-classes.tsv") as badClassFile:
        for c in yagoTaxonomyUp:
            badClassFile.write(c)

if TEST:
    evaluator.compare(FOLDER+"04-yago-facts-to-rename.tsv")
    evaluator.compare(FOLDER+"04-yago-ids.tsv")
    evaluator.compare(FOLDER+"04-yago-bad-classes.tsv")