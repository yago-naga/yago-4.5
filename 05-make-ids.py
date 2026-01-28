"""
Replaces the ids of the facts by YAGO ids

CC-BY 2022-2025 Fabian M. Suchanek

Input:
- 04-yago-facts-to-rename.tsv
- 04-yago-ids.tsv
- 04-yago-bad-classes.tsv

Output:
- 05-yago-final-wikipedia.tsv
- 05-yago-final-beyond-wikipedia.tsv
- 05-yago-final-meta.tsv
- 05-yago-final-taxonomy.tsv
- 05-yago-final-wikipedia-labels.tsv
- 05-yago-final-beyond-wikipedia-labels.tsv

Algorithm:
- load yago-ids.tsv
- run through yago-facts-to-rename.tsv
  - replace the Wikidata ids by YAGO ids
  - write out the facts to the output files
   
"""

##########################################################################
#             Booting
##########################################################################

import sys
import re
import Evaluator
import TsvUtils
import TurtleUtils

TEST=len(sys.argv)>1 and sys.argv[1]=="--test"
FOLDER="test-data/05-make-ids/" if TEST else "yago-data/"

##########################################################################
#             Helper methods
##########################################################################

def isLiteral(entity):
    """ TRUE for literals and external URLs """
    return entity.startswith('"') or entity.startswith('<http://') or entity.startswith('<https://')

def toYagoEntity(entity):
    """ Translates an entity to a YAGO entity, passes through literals, returns NONE otherwise """
    literalValue, _, _, datatype = TurtleUtils.splitLiteral(entity)
    if datatype:
        return '"'+literalValue+'"^^'+toYagoEntity(datatype)
    if literalValue:
        return entity
    if entity.startswith('<http://') or entity.startswith('<https://'):
        return entity
    if entity.startswith("yago:") or entity.startswith("schema:") or entity.startswith("rdfs:") or entity.startswith("xsd:"):
        return entity
    if entity.startswith("_:"):
        # Anonymous members of lists etc.
        if not entity.endswith("_generic_instance"):
            return entity
        # Generic instances
        cls=entity[2:-17]
        cls=yagoIds.get(cls, None)
        if cls==None or cls.find(":")==-1:
            return None
        return cls+"_generic_instance"
    if entity in yagoIds:
        return yagoIds[entity]
    return None
    
def goesToWikipediaVersion(entity):
    """ TRUE if the entity is a literal or has a Wikipedia page or is a generic instance"""
    return isLiteral(entity) or entity in entitiesWithWikipediaPage or entity.endswith("_generic_instance")

wikipediaUrlPattern=re.compile("https://([a-z]+).wikipedia.org/.*")

def isNonEnglishLabel(literal):
    """ TRUE for non-English labels and Wikipedia pages"""
    if literal[2] and literal[2]!='en':
        return True
    if literal[0]:
        match=wikipediaUrlPattern.match(literal[0])
        if match  and  match.group(1)!='en':
                return True                
    return False
    
##########################################################################
#             Main
##########################################################################

with TsvUtils.Timer("Step 05: Renaming YAGO entities"):

    yagoIds={}
    entitiesWithWikipediaPage=set()
    for split in TsvUtils.tsvTuples(FOLDER+"04-yago-ids.tsv", "  Loading YAGO ids"):
        if len(split)<4:
            continue
        yagoIds[split[0]]=split[2]
        if split[3]==". #WIKI":
            entitiesWithWikipediaPage.add(split[2])
    
    for split in TsvUtils.tsvTuples(FOLDER+"04-yago-bad-classes.tsv", "  Removing bad YAGO classes"):
        yagoIds.pop(split[0], None)

    with TsvUtils.TsvFileWriter(FOLDER+"05-yago-final-meta.tsv") as metaFacts:
        with TsvUtils.TsvFileWriter(FOLDER+"05-yago-final-beyond-wikipedia.tsv") as fullFacts:
            with TsvUtils.TsvFileWriter(FOLDER+"05-yago-final-wikipedia.tsv") as wikipediaFacts:
                with TsvUtils.TsvFileWriter(FOLDER+"05-yago-final-wikipedia-labels.tsv") as wikipediaLabelFacts:
                    with TsvUtils.TsvFileWriter(FOLDER+"05-yago-final-beyond-wikipedia-labels.tsv") as fullLabelFacts:
                        previousEntity="Elvis"
                        for split in TsvUtils.tsvTuples(FOLDER+"04-yago-facts-to-rename.tsv", "  Renaming"):
                            if len(split)<3:
                                continue
                            subject=toYagoEntity(split[0])
                            if not subject:
                                # Should not happen
                                continue
                            relation=split[1]
                            object=toYagoEntity(split[2])
                            if not object:
                                # Should not happen
                                continue
                            literal=TurtleUtils.splitLiteral(object)
                            # Write facts to Wikipedia version of YAGO
                            if goesToWikipediaVersion(subject) and (relation=="rdf:type" or goesToWikipediaVersion(object)):
                                if isNonEnglishLabel(literal):
                                    wikipediaLabelFacts.writeFact(subject, relation, object)
                                else:
                                    wikipediaFacts.writeFact(subject, relation, object)
                                if subject.endswith("_generic_instance"):
                                    wikipediaFacts.writeFact(subject, "rdfs:label", f'"{subject[5:-17]}"@en')
                                if subject!=previousEntity and split[0] in yagoIds:
                                   wikipediaFacts.writeFact(subject, "owl:sameAs", split[0])
                            else:
                                if isNonEnglishLabel(literal):
                                    fullLabelFacts.writeFact(subject, relation, object)
                                else:
                                    fullFacts.writeFact(subject, relation, object)
                                if subject!=previousEntity and split[0] in yagoIds:
                                   fullFacts.writeFact(subject, "owl:sameAs", split[0])                
                            # If there is a meta-fact, write it out as well
                            if len(split)>5:
                                if split[4] and split[4]==split[5]:
                                    metaFacts.write("<<", subject, relation, object, ">>", "yago:onDate", split[4], ".")
                                else:
                                    if split[4]: metaFacts.write("<<", subject, relation, object, ">>", "schema:startDate", split[4], ".")
                                    if split[5]: metaFacts.write("<<", subject, relation, object, ">>", "schema:endDate", split[5], ".")
                            if not subject.endswith("_generic_instance"):
                                previousEntity=subject
                    
    with TsvUtils.TsvFileWriter(FOLDER+"05-yago-final-taxonomy.tsv") as taxFacts:
        for split in TsvUtils.tsvTuples(FOLDER+"02-yago-taxonomy-to-rename.tsv", "  Renaming classes"):
            if len(split)<3:
                continue
            subject=toYagoEntity(split[0])
            if not subject:
                # Happens if a class has no label or no instances
                continue
            relation=split[1]
            object=split[2] if relation=="rdf:type" else toYagoEntity(split[2])
            if not object:
                # Happens if a class has no label or no instances
                continue
            # Write taxonomic fact
            taxFacts.writeFact(subject, relation, object)            

if TEST:
    Evaluator.compare(FOLDER+"05-yago-final-wikipedia.tsv")
    Evaluator.compare(FOLDER+"05-yago-final-beyond-wikipedia.tsv")
    Evaluator.compare(FOLDER+"05-yago-final-meta.tsv")
    Evaluator.compare(FOLDER+"05-yago-final-taxonomy.tsv")
    Evaluator.compare(FOLDER+"05-yago-final-wikipedia-labels.tsv")