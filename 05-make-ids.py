"""
Replaces the ids of the facts by YAGO ids

CC-BY 2022-2025 Fabian M. Suchanek

Input:
- 01-yago-taxonomy.ttl
- 02-yago-taxonomy.tsv
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
- 05-yago-final-schema.tsv

Algorithm:
- load yago-ids.tsv
- run through yago-facts-to-rename.tsv and the taxonomy
  - replace the Wikidata ids by YAGO ids
  - write out the facts to the output files
- Expand all units in the schema
"""

##########################################################################
#             Booting
##########################################################################

import sys
import re
import Evaluator
import TsvUtils
import TurtleUtils
import Prefixes
import Schema

TEST=len(sys.argv)>1 and sys.argv[1]=="--test"
FOLDER="test-data/05-make-ids/" if TEST else "yago-data/"
SCHEMA_FILE = "yago-data/01-yago-schema.ttl"

def debug(*message) -> None:
    """ Prints a message if we're in TEST mode"""
    if TEST:
        sys.stdout.buffer.write(b"  DEBUG: ")
        for m in message:
            # Using this instead of print to allow printing unicode chars to pipes
            sys.stdout.buffer.write(str(m).encode('utf8'))
            sys.stdout.buffer.write(b" ")
        print("")

##########################################################################
#             Helper methods
##########################################################################

def isLiteral(entity):
    """ TRUE for literals and external URLs """
    return entity.startswith('"') or entity.startswith('<http://') or entity.startswith('<https://')

def isGenericInstance(entity):
    """ TRUE if this entity is a generic instance"""
    return entity.endswith("_generic_instance")
    
def yagoIdToString(yagoId):
    """ Decodes Unicode character escapes in a YAGO ID and returns a string."""
    if not yagoId:
        return yagoId
    yagoId=yagoId[yagoId.find(':')+1:]
    if yagoId.startswith(Prefixes.namePrefix):
        yagoId = yagoId[len(Prefixes.namePrefix):]
    return re.sub(r'_U([0-9a-fA-F]{4})_', lambda m: chr(int(m.group(1), 16)), yagoId)
    
def toYagoEntity(entity):
    """ Translates an entity to a YAGO entity, passes through literals, returns NONE otherwise """
    literalValue, _, _, datatype = TurtleUtils.splitLiteral(entity)
    if datatype:
        yagoDataType=toYagoEntity(datatype)
        return '"'+literalValue+'"^^'+yagoDataType if yagoDataType else None
    if literalValue:
        if literalValue.startswith(Prefixes.REPLACE_QID_FLAG):
            name=yagoIdToString(toYagoEntity(literalValue[len(Prefixes.REPLACE_QID_FLAG):]))
            return '"'+name+'"' if name else None           
        return entity
    if entity.startswith('<http://') or entity.startswith('<https://'):
        return entity
    if entity.startswith("yago:") or entity.startswith("schema:") or entity.startswith("rdfs:") or entity.startswith("xsd:") or entity.startswith("geo:"):
        return entity
    if entity.startswith("_:"):
        # Anonymous members of lists etc.
        if not isGenericInstance(entity):
            return entity
        # Generic instances
        cls=entity[2:-17]
        cls=yagoIds.get(cls, None)
        if cls==None or cls.find(":")==-1:
            return None
        return cls+"_generic_instance"
    if entity in yagoIds:
        return yagoIds[entity]
    debug("Entity not found",entity)    
    return None
    
def goesToWikipediaVersion(entity):
    """ TRUE if the entity is a literal or has a Wikipedia page or is a generic instance"""
    if isLiteral(entity):
        string, _, _, unit = TurtleUtils.splitLiteral(entity)    
        return unit is None or not unit.startswith("yago:") or goesToWikipediaVersion(unit)
    return entity in entitiesWithWikipediaPage or isGenericInstance(entity)

wikipediaUrlPattern=re.compile("https://([a-z-]+)\\.wiki.*")

def isNonEnglishLabel(literal):
    """ TRUE for non-English labels and Wiki-pages"""
    if literal[2] and literal[2]!='en' and literal[2]!='mul':
        return True
    if literal[0]:
        match=wikipediaUrlPattern.match(literal[0])
        if match  and  match.group(1)!='en':
                return True                
    return False

def childrenOf(cls, taxonomyDown):
    """ Yields all children of this class, excluding the class itself """
    for subclass in taxonomyDown.get(cls,[]):
        yield subclass
        yield from childrenOf(subclass, taxonomyDown)
        
##########################################################################
#             Main
##########################################################################

with TsvUtils.Timer("Step 05: Renaming YAGO entities"):

    # Load YAGO ids
    
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
    
    # Simplify ids
    
    print("  Simplifying ids... ", flush=True, end='')
    simplifiedIds=set()
    for entity in yagoIds:
        entityId=yagoIds[entity]
        if entityId not in entitiesWithWikipediaPage:
            pos=entityId.rfind("_Q")
            if pos!=-1:
                entityId=entityId[0:pos]
                if entityId not in simplifiedIds and entityId not in entitiesWithWikipediaPage:
                    yagoIds[entity]=entityId
                    simplifiedIds.add(entityId)
    print("done")

    # Write out facts
    
    yagoUnits={}
    
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
                                # Happens for empty classes
                                continue
                            relation=split[1]
                            obj=toYagoEntity(split[2])
                            if not obj:
                                # Should not happen
                                continue
                            # Register units
                            if relation==Prefixes.rdfType and obj.startswith(Prefixes.yagoUnit):
                                if obj not in yagoUnits:
                                    yagoUnits[obj]=set()
                                yagoUnits[obj].add(subject)
                            literal=TurtleUtils.splitLiteral(obj)
                            # Write facts to Wikipedia version of YAGO
                            if goesToWikipediaVersion(subject) and (relation==Prefixes.rdfType or goesToWikipediaVersion(obj)):
                                if isNonEnglishLabel(literal):
                                    wikipediaLabelFacts.writeFact(subject, relation, obj)
                                else:
                                    wikipediaFacts.writeFact(subject, relation, obj)
                                if isGenericInstance(subject):
                                    wikipediaFacts.writeFact(subject, "rdfs:label", f'"{subject[5:-17].replace('_', ' ')}"@en')
                                if subject!=previousEntity and split[0] in yagoIds:
                                   wikipediaFacts.writeFact(subject, "owl:sameAs", split[0])
                            else:
                                if isNonEnglishLabel(literal):
                                    fullLabelFacts.writeFact(subject, relation, obj)
                                else:
                                    fullFacts.writeFact(subject, relation, obj)
                                if subject!=previousEntity and split[0] in yagoIds:
                                   fullFacts.writeFact(subject, "owl:sameAs", split[0])                
                            # If there is a meta-fact, write it out as well
                            if len(split)>5:
                                if split[4] and split[4]==split[5]:
                                    metaFacts.writeMetaFact(subject, relation, obj, "yago:onDate", split[4])
                                else:
                                    if split[4]: metaFacts.writeMetaFact(subject, relation, obj, "schema:startDate", split[4])
                                    if split[5]: metaFacts.writeMetaFact(subject, relation, obj, "schema:endDate", split[5])
                            if not isGenericInstance(subject):
                                previousEntity=subject
     
    # Write out taxonomy
    
    with TsvUtils.TsvFileWriter(FOLDER+"05-yago-final-taxonomy.tsv") as taxFacts:
        for split in TsvUtils.tsvTuples(FOLDER+"02-yago-taxonomy-to-rename.tsv", "  Renaming classes"):
            if len(split)<3:
                continue
            subject=toYagoEntity(split[0])
            if not subject  or subject==Prefixes.yagoPersonName:
                # Happens if a class has no label or no instances
                continue
            relation=split[1]
            obj=split[2] if relation==Prefixes.rdfType else toYagoEntity(split[2])
            if not obj:
                # Happens if a class has no label or no instances
                continue
            # Happened with yago:Award rdfs:subClassOf yago:Award...
            if subject==obj:
                continue
            # Write taxonomic fact            
            taxFacts.writeFact(subject, relation, obj)              
    
    # Write out schema
    
    yagoSchema = Schema.YagoSchema(SCHEMA_FILE) 
    print("  Adding datatypes to schema...", flush=True, end='')
    for prop in yagoSchema.properties.values():
        if prop.isDatatype:
            newDataTypes=set()
            for datatype in prop.objectTypes:
                if datatype in yagoUnits:
                    newDataTypes.update(yagoUnits[datatype])
                else:
                    newDataTypes.add(datatype)
            prop.objectTypes=newDataTypes
    print("done")            
    print("  Writing out schema...", flush=True, end='')
    yagoSchema.writeToFile(FOLDER+"05-yago-final-schema.ttl")
    print("done")
    
if TEST:
    Evaluator.compare(FOLDER+"05-yago-final-wikipedia.tsv")
    Evaluator.compare(FOLDER+"05-yago-final-beyond-wikipedia.tsv")
    Evaluator.compare(FOLDER+"05-yago-final-meta.tsv")
    Evaluator.compare(FOLDER+"05-yago-final-taxonomy.tsv")
    Evaluator.compare(FOLDER+"05-yago-final-wikipedia-labels.tsv")