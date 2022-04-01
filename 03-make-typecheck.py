"""
Typechecks the facts of YAGO

(c) 2022 Fabian M. Suchanek

Call:
  python3 make-typecheck.py

Input:
- yago-taxonomy.ttl
- yago-facts-to-type-check.tsv

Output:
- yago-facts-unlabeled.tsv (type checked YAGO facts without correct labels)

Algorithm:
- run through all entities of yago-facts-to-type-check.tsv, load classes
- run through all facts in yago-facts-to-type-check.tsv, do type check
    - write out facts that fulfill the constraints to yago-facts-2.ttl
   
"""

TEST=True
FOLDER="test-data/" if TEST else ""

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
from collections import defaultdict
print("done")

print("  Loading YAGO taxonomy...", end="", flush=True)
yagoTaxonomy=Graph()
utils.parse(FOLDER+"yago-taxonomy.ttl", format="turtle")
print("done")

print("  Loading YAGO instances...", end="", flush=True)
yagoInstances=defaultdict(set)
with open(FOLDER+"yago-facts-to-type-check.tsv", mode='rt', encoding='UTF-8') as file:
    for line in file:
        line=line.rstrip()
        if "\trdf:type\t" in line:
            split=line.split("\t")
            yagoInstances[split[0]].add(split[2])
print("done")

##########################################################################
#             Main
##########################################################################

def isSubclassOf(c1, c2):
    if c1==c2:
        return True
    for superclass in yagoTaxonomy.objects(c1, RDFS.subclassOf):
        if isSubclassOf(c1, superclass):
            return True
    return False
    
def instanceOf(obj, cls):
    return any(isSubclassOf(c, cls) for c in yagoInstances[obj])
    
print("  Type-checking facts...", end="", flush=True)
with open(FOLDER+"yago-facts-unlabeled.tsv", "wt", encoding="utf=8") as out:
    with open(FOLDER+"yago-facts-to-type-check", "rt", encoding="utf=8") as input:
        currentTopic=""
        currentLabel=""
        currentWikipediaPage=""
        wroteFacts=False
        for line in input:
            split=line.rstrip().split("\t")
            if split[0]!=currentTopic:
                if wroteFacts:
                    if currentWikipediaPage:
                        out.write(currentTopic+"\towl:sameAs\tyago:"+yagoIdFromWikipediaPage(currentWikipediaPage)+"\n")
                    elif currentLabel:
                        out.write(currentTopic+"\towl:sameAs\tyago:"+yagoIdFromLabel(currentWikipediaPage)+"\n")
                    else:
                        out.write(currentTopic+"\towl:sameAs\tyago:"+yagoIdFromWikidataID(currentTopic)+"\n")
                currentTopic=split[0]
                currentLabel=""
                currentWikipediaPage=""
                wroteFacts=False
            if split[1]=="rdfs:label" and split[2].endswith('"@en'):
                currentLabel=split[2]
            elif split[1]=="schema:mainEntityOfPage" and split[2].startswith('https://en.wikipedia.org/'):
                currentWikipediaPage=split[2]
            if len(split)==3:
                out.write(split[0]+"\t"+split[1]+"\t"+split[2]+"\n")
                wroteFacts=True
                continue            
            classes=split[4].split(", ")
            if any(instanceOf(split[2],c) for c in classes):
                out.write(split[0]+"\t"+split[1]+"\t"+split[2]+"\n")
                wroteFacts=True
        
print("done")

print("done")
