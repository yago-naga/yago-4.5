"""
Produces statistics about YAGO entities and predicates, and extracts samples

CC-BY 2022-2025 Fabian M. Suchanek

Input:
- 01-yago-final-schema.ttl
- 05-yago-final-beyond-wikipedia.tsv
- 05-yago-final-wikipedia.tsv
- 05-yago-final-taxonomy.tsv
- Log files

Output:
- 06-statistics.txt
- 06-taxonomy.html
- 06-upper-taxonomy.html
- 06-sample-entities.ttl
- 06-sample-logs.tsv

Algorithm:
- load taxonomy
- run through yago-final-full
  - update statistics
  - sample entities
- print statistics and trees
   
"""

##########################################################################
#             Booting
##########################################################################

import sys
import glob
import re
import Evaluator
import itertools
import TurtleUtils
import TsvUtils
import random
import os
import Prefixes
from Schema import YagoSchema
from collections import defaultdict

TEST=len(sys.argv)>1 and sys.argv[1]=="--test"
FOLDER="test-data/06-make-statistics/" if TEST else "yago-data/"

# Predicates that are excluded for fact counting
excludePredicates=["rdfs:label", "rdfs:comment", "rdf:type", "schema:url", "owl:sameAs", "schema:alternateName"]

def getFirst(myList):
    """ Returns the first element of an iterable or none """    
    for o in myList:
        return o
    return None

##########################################################################
#             Full Taxonomy as HTML
##########################################################################

def getSuperClasses_(cls, classes, yagoTaxonomyUp, counter=0):
    """Adds all superclasses of a class <cls> (including <cls>) to the set <classes>"""
    classes.add(cls)
    if counter>200:
        print("  Warning: recursion overflow in taxonomy with",cls,"and",classes)
        return
    if cls not in yagoTaxonomyUp:
        return
    for sc in yagoTaxonomyUp[cls]:
        getSuperClasses_(sc, classes, yagoTaxonomyUp, counter+1)        
    return

def getSuperClasses(entityFacts, yagoTaxonomyUp):
    """ Returns the classes and all superclasses of the main entity"""
    superClasses=set()    
    for c in entityFacts.objectsOf(mainEntity, Prefixes.rdfType):
        getSuperClasses_(c, superClasses, yagoTaxonomyUp) 
    return superClasses
    
def _printTaxonomy(writer, yagoTaxonomyDown, class2num, cls=Prefixes.schemaThing):
    """ Prints the taxonomy to the writer. <cls> is the class to start with, i.e., the top-level class. """
    if cls not in yagoTaxonomyDown:
        writer.write(f"<li>{cls.replace('yago:','y:')}: {str(class2num.get(cls,0))}\n")
        return
    writer.write(f"<li><details style='margin-left: 2em'><summary style='margin-left: -2em'>{cls.replace('yago:','y:')}: {str(class2num.get(cls,0))}</summary><ul>\n")
    for subclass in yagoTaxonomyDown.get(cls, []):
        _printTaxonomy(writer, yagoTaxonomyDown, class2num, subclass)
    writer.write("</ul></details>\n")

def printTaxonomy(file, yagoTaxonomyDown, class2num):
    """ Prints the full taxonomy to the file """
    with open(file, "wt", encoding="UTF-8") as writer:
        writer.write("""
<!DOCTYPE html>
<html>
 <head>
  <meta charset=utf-8>
  <meta name=viewport content="width=device-width, initial-scale=1.0">   
  <title>
   YAGO Taxonomy
  </title>
  <style>
  ul {list-style-type:none}
  </style>
 </head>      
 <body>
 <h1>YAGO Taxonomy</h1>
 <ul>\n""")
        _printTaxonomy(writer, yagoTaxonomyDown, class2num)
        writer.write("</ul></body>\n</html>")

##########################################################################
#             Top-level taxonomy as HTML
##########################################################################
 
def printUpperTaxonomy(file, yagoSchema):
    """ Visualizes the top-level taxonomy as an HTML document"""
    with open(file, "wt", encoding="UTF-8") as writer:
        writer.write("""
<h1>YAGO Schema</h1> 
This is the top-level taxonomy of classes of YAGO 4.5, together with their properties.
 <ul style='list-style-type: none'>
        """)
        def add_node(yagoClass):
            # Head
            writer.write(f"<li><details style='margin-left: 2em'{' open' if yagoClass.identifier=='schema:Thing' else ''}><summary style='font-weight:bold; margin-left: -2em'>{yagoClass.identifier}</summary><details style='margin-left: 2em'><summary style='margin-left: -2em'>Outgoing properties</summary><ul style='list-style-type: none'>\n")
            
            # Outgoing properties
            for yagoProperty in sorted(yagoClass.properties):
                writer.write(f"<li>- {yagoProperty.identifier} &rarr;{'<sup>1</sup>' if yagoProperty.maxCount or yagoProperty.uniqueLang else ''} {', '.join(sorted(yagoProperty.objectTypes))}")
            writer.write("</ul></details>\n<details style='margin-left: 2em'><summary style='margin-left: -2em'>Incoming properties</summary><ul style='list-style-type: none'>\n")
            
            # Incoming properties
            for yagoProperty in sorted(prop for prop in yagoSchema.properties.values() if yagoClass.identifier in prop.objectTypes):                
                 writer.write(f'<li>- ({", ".join(sorted(yagoProperty.subjectTypes))}) {yagoProperty.identifier}')
            writer.write(f"</ul></details><details style='margin-left: 2em'{' open' if yagoClass.identifier=='schema:Thing' else ''}><summary style='margin-left: -2em'>Subclasses</summary><ul style='list-style-type: none'>\n")
            
            # Subclasses
            for subclass in sorted(cls for cls in yagoSchema.classes.values() if yagoClass in cls.superClasses):
                add_node(subclass)
            writer.write("</ul></details></details>\n")
        add_node(yagoSchema.classes["schema:Thing"])
        writer.write("</ul>")
 
##########################################################################
#             Main
##########################################################################

# Number of example entities
NUM_SAMPLES=200

with TsvUtils.Timer("Step 06: Collecting YAGO statistics"):

    # Load YAGO schema
    yagoSchema = YagoSchema(FOLDER+"01-yago-final-schema.ttl")

    # Load YAGO taxonomy
    yagoTaxonomyDown={}
    yagoTaxonomyUp={}
    for triple in TsvUtils.tsvTuples(FOLDER+"05-yago-final-taxonomy.tsv", "  Loading YAGO taxonomy"):
        if len(triple)<3:
            continue
        if triple[0] not in yagoTaxonomyUp:
            yagoTaxonomyUp[triple[0]]=set()            
        yagoTaxonomyUp[triple[0]].add(triple[2])
        if triple[2] not in yagoTaxonomyDown:
            yagoTaxonomyDown[triple[2]]=set()
        yagoTaxonomyDown[triple[2]].add(triple[0])

    # Initialize counters
    predicate2num={}
    class2num={}
    samples=[]
    entities=set()
    numGenericInstances=0
    
    # Run through the facts
    for fileName in ["05-yago-final-wikipedia.tsv", "05-yago-final-beyond-wikipedia.tsv"]:
        print("  Counting generic instances in",fileName, "...", end='',flush=True)
        with open(FOLDER+fileName, "rt", encoding="UTF-8") as factFile:
            for line in factFile:
                if "_generic_instance\trdf:type" in line:
                   numGenericInstances+=1 
        print("done")
        for entityFacts in TurtleUtils.tsvEntities(FOLDER+fileName, "  Parsing "+fileName):
            mainEntity=entityFacts.mainSubject()
            # We do not care about classes here
            if (mainEntity, Prefixes.rdfType, Prefixes.rdfsClass) in entityFacts:
                continue
            entities.add(mainEntity)
            # Count predicates
            for p in entityFacts.predicatesOf(mainEntity):
                if p not in predicate2num:
                    predicate2num[p]=0
                predicate2num[p]+=len(entityFacts.objectsOf(mainEntity,p))
            superClasses=getSuperClasses(entityFacts, yagoTaxonomyUp)
            for c in superClasses:
                if c not in class2num:
                    class2num[c]=0
                class2num[c]+=1 
            if len(samples)<NUM_SAMPLES:
                for c in superClasses:
                    entityFacts.add((mainEntity, 'rdf:type', c))
                samples.append(entityFacts)
            else:
                randomNumber=int(random.random()*len(entities))
                if randomNumber<NUM_SAMPLES:    
                    for c in superClasses:
                        entityFacts.add((mainEntity, 'rdf:type', c))
                    samples[randomNumber]=entityFacts        
            
    print("  Writing out sample entities... ",end="",flush=True)    
    with open(FOLDER+"06-sample-entities.ttl", "wt", encoding="UTF-8") as sampleFile:
        for sample in samples:
            sample.printToWriter(sampleFile)
    print("done")

    numMetaFacts=0
    for triple in TsvUtils.tsvTuples(FOLDER+"05-yago-final-meta.tsv", "  Counting meta facts"):
        numMetaFacts += 1
    
    print("  Computing dump size... ",end="",flush=True)    
    dumpSize=0
    for f in glob.glob(FOLDER+"*final*.tsv"):
        dumpSize+=os.path.getsize(f)
    print("done")
    
    print("  Sampling from the logs...")
    wikidata2yago={}
    for split in TsvUtils.tsvTuples(FOLDER+"04-yago-ids.tsv", "    Loading YAGO ids"):
        if len(split)<4:
            continue
        wikidata2yago[split[0]]=split[2]
    reasonsForExclusion={}
    with open(FOLDER+"06-sample-logs.tsv", "wt", encoding="UTF=8") as sampleFile:
        for logFile in glob.glob(FOLDER+"*.log"):
            logFileName=logFile[logFile.rfind("/")+1:]
            sampleFile.write("# ---- "+logFileName+" ----\n\n")
            samples=[]
            reasonsForExclusion[logFileName]={}
            counter=0
            for split in TsvUtils.tsvTuples(logFile, "    Sampling from "+logFileName):
                if len(split)<7:
                    continue
                counter+=1                    
                reason=split[6][1:-1]
                if ": " in reason:
                    reason=reason[0:reason.find(": ")]                
                # Handle legacy cases
                elif reason.startswith("Subclass ("):
                    reason="Subclass is disjoint from ancestor of superclass"
                elif reason.startswith("Domain check"):
                    reason="Domain check failed"
                elif reason.startswith("object is"):
                    reason="Range check failed"    
                if reason not in reasonsForExclusion[logFileName]:
                    reasonsForExclusion[logFileName][reason]=0
                reasonsForExclusion[logFileName][reason]+=1
                # We sample reasons only from the detailed ones
                if not ": " in split[6]:
                    continue
                if len(samples)<NUM_SAMPLES:
                    samples.append(split)
                else:
                    randomNumber=int(random.random()*counter)
                    if randomNumber<NUM_SAMPLES:    
                        samples[randomNumber]=split
            for sample in samples:
                sampleFile.write("\t".join(sample)+"\n# ")
                for i in [1,2,3]:
                    sampleFile.write(wikidata2yago.get(sample[i],sample[i])+"\t")
                sampleFile.write("\n\n")
            if not samples:
                sampleFile.write("  # no exclusion reasons with details\n\n")              
    print("  done")

    print("  Writing out statistics... ",end="",flush=True)    
    with open(FOLDER+"06-statistics.txt", "wt", encoding="UTF-8") as writer:
        writer.write("YAGO 4.6 statistics\n\n")
        writer.write("Dump size: "+str(dumpSize/1024/1024/1024)+" GB\n\n")
        writer.write("Total number of entities (without generic): "+str(len(entities))+"\n\n")
        writer.write("Generic entities: "+str(numGenericInstances)+"\n\n")
        writer.write("Total number of classes: "+str(len(yagoTaxonomyUp))+"\n\n")
        writer.write("Disjointness statements: "+str(sum(len(yagoClass.disjointWith) for yagoClass in yagoSchema.classes.values()))+"\n\n")
        writer.write("Total number of facts (excluding labels etc.): "+str(sum([predicate2num[p] for p in predicate2num if p not in excludePredicates]))+"\n\n")
        writer.write("Avg number of facts (excluding labels etc.) per entity: "+str(sum([predicate2num[p] for p in predicate2num if p not in excludePredicates])/len(entities))+"\n\n")
        writer.write("Total number of meta facts: "+str(numMetaFacts)+"\n\n")
        writer.write("Total number of predicates: "+str(len(predicate2num))+"\n\n")
        writer.write("Predicates:\n")
        for pred in sorted(predicate2num.items(), key=lambda x:-x[1]):
            writer.write("  "+pred[0]+": "+str(pred[1])+"\n") 
        writer.write("\nExclusion reasons:\n")
        for file in reasonsForExclusion:
            writer.write("  "+file+":\n")
            for reason in sorted(reasonsForExclusion[file].items(), key=lambda x:-x[1]):
                writer.write("    "+reason[0]+": "+str(reason[1])+"\n")
    print("done")
     
    print("  Writing out taxonomy... ",end="",flush=True)    
    printTaxonomy(FOLDER+"06-taxonomy.html", yagoTaxonomyDown, class2num)
    printUpperTaxonomy(FOLDER+"06-upper-taxonomy.html", yagoSchema)
    print("done")
        
if TEST:
    Evaluator.compare(FOLDER+"06-statistics.txt", FOLDER+"06-statistics-gold.txt")
    Evaluator.compare(FOLDER+"06-taxonomy.html", FOLDER+"06-taxonomy-gold.html")
    Evaluator.compare(FOLDER+"06-upper-taxonomy.html", FOLDER+"06-upper-taxonomy-gold.html")