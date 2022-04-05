"""
Typechecks the facts of YAGO

(c) 2022 Fabian M. Suchanek

Call:
  python3 make-typecheck.py

Input:
- yago-taxonomy.ttl
- yago-facts-to-type-check.tsv

Output:
- yago-facts-unlabeled.tsv (type checked YAGO facts without correct ids)
- yago-ids.tsv (maps Wikidata ids to YAGO ids)

Algorithm:
- run through all entities of yago-facts-to-type-check.tsv, load classes
- run through all facts in yago-facts-to-type-check.tsv, do type check
    - write out facts that fulfill the constraints to yago-facts-unlabeled.tsv
    - if there are any such facts, write out the id to yago-ids.tsv
   
"""

TEST=True
FOLDER="test-data/03-make-typecheck/" if TEST else "yago-data/"

##########################################################################
#             Booting
##########################################################################

print("Type-checking YAGO facts...")
print("  Importing...",end="", flush=True)
# Importing alone takes so much time that a status message is in order...
from rdflib import URIRef, RDFS, RDF, Graph, Literal, XSD
import utils
import sys
import re
import unicodedata
from collections import defaultdict
print("done")

print("  Loading YAGO taxonomy...", end="", flush=True)
yagoTaxonomy=Graph()
yagoTaxonomy.parse(FOLDER+"yago-taxonomy.ttl", format="turtle")
print("done")

yagoInstances=defaultdict(set)
for line in utils.linesOfFile(FOLDER+"yago-facts-to-type-check.tsv", "  Loading YAGO instances"):
    line=line.rstrip()
    if "\trdf:type\t" in line:
        split=line.split("\t")
        yagoInstances[split[0]].add(split[2])

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
    if currentWikipediaPage:
        out.write(currentTopic+"\tyago:"+yagoIdFromWikipediaPage(currentWikipediaPage)+"\tWIKI\n")
    elif currentLabel:
        out.write(currentTopic+"\tyago:"+yagoIdFromLabel(currentTopic,currentLabel)+"\tOTHER\n")
    else:
        out.write(currentTopic+"\tyago:"+yagoIdFromWikidataId(currentTopic)+"\tOTHER\n")
  
##########################################################################
#             Main
##########################################################################

def isSubclassOf(c1, c2):
    if c1==c2:
        return True
    for superclass in yagoTaxonomy.objects(c1, RDFS.subClassOf):
        if isSubclassOf(c1, superclass):
            return True
    return False
    
def instanceOf(obj, cls):
    return any(isSubclassOf(c, cls) for c in yagoInstances[obj])
    
with open(FOLDER+"yago-facts-unlabeled.tsv", "wt", encoding="utf=8") as out:
    with open(FOLDER+"yago-ids.tsv", "wt", encoding="utf=8") as idsFile:
        currentTopic=""
        currentLabel=""
        currentWikipediaPage=""
        wroteFacts=False # True if the entity had any valid facts
        for line in utils.linesOfFile(FOLDER+"yago-facts-to-type-check.tsv", "  Type-checking facts"):
            split=line.rstrip().split("\t")
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
            if len(split)==3:
                out.write(split[0]+"\t"+split[1]+"\t"+split[2]+"\n")
                wroteFacts=True
                continue            
            classes=split[4].split(", ")
            if any(instanceOf(split[2],c) for c in classes):
                out.write(split[0]+"\t"+split[1]+"\t"+split[2]+"\n")
                wroteFacts=True
        # Also flush the ids of the last entity...
        if wroteFacts:
            writeYagoId(idsFile, currentTopic, currentLabel, currentWikipediaPage)
print("done")
