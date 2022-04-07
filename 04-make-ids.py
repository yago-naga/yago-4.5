"""
Replaces the ids of the facts by YAGO ids

(c) 2022 Fabian M. Suchanek

Input:
- yago-facts-unlabeled.tsv
- yago-ids.tsv

Output:
- yago-final-wikipedia.ttl
- yago-final-full.ttl

Algorithm:
- load yago-ids.tsv
- run through yago-facts-unlabeled.tsv
  - replace the Wikidata ids by YAGO ids
  - write out the facts to the output files
   
"""

TEST=True
FOLDER="test-data/04-make-ids/" if TEST else "yago-data/"

##########################################################################
#             Booting
##########################################################################

import utils
import sys

print("Renaming YAGO entities...")

yagoIds={}
entitiesWithWikipediaPage=set()
for line in utils.linesOfFile(FOLDER+"yago-ids.tsv", "  Loading YAGO ids"):
    line=line.rstrip()
    split=line.split("\t")
    yagoIds[split[0]]=split[1]
    if split[2]=="WIKI":
        entitiesWithWikipediaPage.add(split[1])

##########################################################################
#             Helper methods
##########################################################################

def isLiteral(entity):
    """ TRUE for literals and external URLs """
    return entity.startswith('"') or entity.startswith('<http://') or entity.startswith('<https://')

def toYagoEntity(entity):
    """ Translates an entity to a YAGO entity, passes through literals, returns NONE otherwise """
    if entity.startswith('"'):
        return entity
    if entity.startswith('<http://') or entity.startswith('<https://'):
        return entity
    if entity.startswith("yago:") or entity.startswith("schema:") or entity.startswith("bioschema:"):
        return entity
    if entity in yagoIds:
        return yagoIds[entity]
    return None

def hasWikipediaPage(entity):
    """ TRUE if the entity is a literal or has a Wikipedia page """
    return isLiteral(entity) or entity in entitiesWithWikipediaPage
    
##########################################################################
#             Main
##########################################################################
    
with open(FOLDER+"yago-final-full.ttl", "wt", encoding="utf=8") as fullFacts:
    with open(FOLDER+"yago-final-wikipedia.ttl", "wt", encoding="utf=8") as wikipediaFacts:
        fullFacts.write(utils.prefixes)
        wikipediaFacts.write(utils.prefixes)        
        for line in utils.linesOfFile(FOLDER+"yago-facts-unlabeled.tsv", "  Renaming"):
            split=line.rstrip().split("\t")
            if len(split)<3:
                continue
            subject=toYagoEntity(split[0])
            if not subject:
                # Should not happen
                print("Entity does not appear in YAGO:", split[0])
                continue
            relation=split[1]
            object=split[2] if relation=="rdf:type" else toYagoEntity(split[2])
            if not object:
                # Should not happen
                print("Entity does not appear in YAGO:", split[2])
                continue
            # Write facts to Wikipedia version of YAGO
            if hasWikipediaPage(subject) and (relation=="rdf:type" or hasWikipediaPage(object)):
                wikipediaFacts.write(subject+"\t"+relation+"\t"+object+"\t.\n")
            # In any case, write (also) to the full version of YAGO
            fullFacts.write(subject+"\t"+relation+"\t"+object+"\t.\n")
print("done")
