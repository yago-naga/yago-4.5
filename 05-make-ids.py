"""
Replaces the ids of the facts by YAGO ids

(c) 2022 Fabian M. Suchanek

Input:
- 03-yago-facts-to-rename.tsv
- 03-yago-ids.tsv

Output:
- 04-yago-final-wikipedia.tsv
- 04-yago-final-full.tsv
- 04-yago-final-meta.tsv

Algorithm:
- load yago-ids.tsv
- run through yago-facts-to-rename.tsv
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
import evaluator

print("Renaming YAGO entities...")

yagoIds={}
entitiesWithWikipediaPage=set()
for split in utils.readTsvTuples(FOLDER+"03-yago-ids.tsv", "  Loading YAGO ids"):
    if len(split)<4:
        continue
    yagoIds[split[0]]=split[2]
    if split[3]==". #WIKI":
        entitiesWithWikipediaPage.add(split[2])

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

with utils.TsvFileWriter(FOLDER+"04-yago-final-meta.tsv") as metaFacts:
    with utils.TsvFileWriter(FOLDER+"04-yago-final-full.tsv") as fullFacts:
        with utils.TsvFileWriter(FOLDER+"04-yago-final-wikipedia.tsv") as wikipediaFacts:
            for split in utils.readTsvTuples(FOLDER+"03-yago-facts-to-rename.tsv", "  Renaming"):
                if len(split)<3:
                    continue
                subject=toYagoEntity(split[0])
                if not subject:
                    # Should not happen
                    # print("Entity does not appear in YAGO:", split[0])
                    continue
                relation=split[1]
                object=split[2] if relation=="rdf:type" else toYagoEntity(split[2])
                if not object:
                    # Should not happen
                    print("Entity does not appear in YAGO:", split[2])
                    continue
                # Write facts to Wikipedia version of YAGO
                if hasWikipediaPage(subject) and (relation=="rdf:type" or hasWikipediaPage(object)):
                    wikipediaFacts.writeFact(subject, relation, object)
                # In any case, write (also) to the full version of YAGO
                fullFacts.writeFact(subject, relation, object)
                # If there is a meta-fact, write it out as well
                if len(split)>5:
                    metaFacts.write("<<", subject, relation, object, ">>", "schema:startDate", split[4])
                    metaFacts.write("<<", subject, relation, object, ">>", "schema:endDate", split[5])
                    
print("done")

if TEST:
    evaluator.compare(FOLDER+"04-yago-final-wikipedia.tsv")
    evaluator.compare(FOLDER+"04-yago-final-full.tsv")
    evaluator.compare(FOLDER+"04-yago-final-meta.tsv")
    