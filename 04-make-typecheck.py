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

Algorithm:
- run through all entities of yago-facts-to-type-check.tsv, load classes
- run through all facts in yago-facts-to-type-check.tsv, do type check
    - write out facts that fulfill the constraints to yago-facts-to-rename.tsv
    - if there are any such facts, write out the id to yago-ids.tsv
   
"""

TEST=True
FOLDER="test-data/04-make-typecheck/" if TEST else "yago-data/"

##########################################################################
#             Booting
##########################################################################

print("Type-checking YAGO facts...")
print("  Importing...",end="", flush=True)
# Importing alone takes so much time that a status message is in order...
import sys
import TsvUtils
import re
import unicodedata
import evaluator
from collections import defaultdict
print("done")

yagoTaxonomyUp=defaultdict(set)
for tuple in TsvUtils.tsvTuples(FOLDER+"02-yago-taxonomy-to-rename.tsv", "  Loading YAGO taxonomy"):
    if len(tuple)>3:
        yagoTaxonomyUp[tuple[0]].add(tuple[2])

yagoInstances=defaultdict(set)
for tuple in TsvUtils.tsvTuples(FOLDER+"03-yago-facts-to-type-check.tsv", "  Loading YAGO instances"):
    if len(tuple)>2 and tuple[1]=="rdf:type":
        yagoInstances[tuple[0]].add(tuple[2])

##########################################################################
#             YAGO ids
##########################################################################

def legal(char):
    """ TRUE if a character is a valid CURIE character. We're very restrictive here to make all parsers work. """
    category=unicodedata.category(char)[0]
    return char in "()_.,+-" or category in "LN"
    
def yagoIdFromWikipediaPage(wikipediaPageTitle):
    """ Creates a YAGO id from a Wikipedia page title"""
    result=""
    for c in wikipediaPageTitle:
        if legal(c):
            result+=c
        else:
            result+="_"
    return result

def yagoIdFromLabel(wikidataEntity,label):
    """ Creates a YAGO id from a Wikidata entity and label """
    result=""
    for c in label:
        if legal(c):
            result+=c
        else: 
            result+="_"
    return result+"_"+wikidataEntity[4:]

def yagoIdFromWikidataId(wikidataEntity):
    """ Creates a YAGO id from a Wikidata entity """
    return wikidataEntity[4:]

def writeYagoId(out, currentTopic, currentLabel, currentWikipediaPage):
    """ Writes wd:Q303 owl:sameAs yago:Elvis """ 
    # Don't print ids for built-in classes
    if currentTopic.startswith("schema:"):
        return
    if currentWikipediaPage:
        out.write(currentTopic,"owl:sameAs","yago:"+yagoIdFromWikipediaPage(currentWikipediaPage),". #WIKI")
    elif currentLabel:
        out.write(currentTopic,"owl:sameAs","yago:"+yagoIdFromLabel(currentTopic,currentLabel),". #OTHER")
    else:
        out.write(currentTopic,"owl:sameAs","yago:"+yagoIdFromWikidataId(currentTopic),". #OTHER")
  
##########################################################################
#             Main
##########################################################################

def isSubclassOf(c1, c2):
    if c1==c2:
        return True    
    for superclass in yagoTaxonomyUp[c1]:
        if isSubclassOf(superclass, c2):
            return True
    return False
    
def instanceOf(obj, cls):
    return any(isSubclassOf(c, cls) for c in yagoInstances[obj])
    
with TsvUtils.TsvFileWriter(FOLDER+"04-yago-facts-to-rename.tsv") as out:
    with TsvUtils.TsvFileWriter(FOLDER+"04-yago-ids.tsv") as idsFile:
        currentTopic=""
        currentLabel=""
        currentWikipediaPage=""
        wroteFacts=False # True if the entity had any valid facts
        for split in TsvUtils.tsvTuples(FOLDER+"03-yago-facts-to-type-check.tsv", "  Type-checking facts"):
            if len(split)<3:
                continue
            if split[0]!=currentTopic:
                if wroteFacts:
                    writeYagoId(idsFile, currentTopic, currentLabel, currentWikipediaPage)
                currentTopic=split[0]
                currentLabel=""
                currentWikipediaPage=""
                wroteFacts=False
            if split[1]=="rdfs:label" and split[2].endswith('"@en'):
                currentLabel=split[2][1:-4]
            elif split[1]=="schema:mainEntityOfPage" and split[2].startswith('<https://en.wikipedia.org/wiki/'):
                currentWikipediaPage=split[2][31:-1]
            startDate=split[5] if len(split)>5 else ""
            endDate=split[6] if len(split)>6 else ""
            classes=split[4].split(", ") if len(split)>4 and len(split[4])>0 else None
            if classes is None or any(instanceOf(split[2],c) for c in classes):
                out.write(split[0], split[1], split[2], ". #", startDate, endDate)
                wroteFacts=True
        # Also flush the ids of the last entity...
        if wroteFacts:
            writeYagoId(idsFile, currentTopic, currentLabel, currentWikipediaPage)
print("done")

if TEST:
    evaluator.compare(FOLDER+"04-yago-facts-to-rename.tsv")
    evaluator.compare(FOLDER+"04-yago-ids.tsv")