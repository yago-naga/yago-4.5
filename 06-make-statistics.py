"""
Produces statistics about YAGO entities and predicates, and extracts samples

CC-BY 2022-2025 Fabian M. Suchanek

Input:
- 01-yago-final-schema.ttl
- 05-yago-final-beyond-wikipedia.tsv
- 05-yago-final-wikipedia.tsv
- 05-yago-final-taxonomy.tsv

Output:
- 06-statistics.txt
- 06-taxonomy.html
- 06-upper-taxonomy.html
- 06-sample-entities.ttl

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

def getSuperClasses(cls, classes, yagoTaxonomyUp, pathsToRoot):
    """Adds all superclasses of a class <cls> (including <cls>) to the set <classes>"""
    classes.add(cls)
    # Make a check before because it's a defaultdict,
    # which would create cls if it's not there
    if cls==Prefixes.schemaThing:
        pathsToRoot[0]+=1
    if cls in yagoTaxonomyUp:
        for sc in yagoTaxonomyUp[cls]:
            getSuperClasses(sc, classes, yagoTaxonomyUp, pathsToRoot)

def _printTaxonomy(writer, cls=Prefixes.schemaThing):
    """ Prints the taxonomy to the writer. <cls> is the class to start with, i.e., the top-level class. """
    if cls not in yagoTaxonomyDown:
        writer.write(f"<li>{cls.replace('yago:','y:')}: {str(classStats.get(cls,0))}\n")
        return
    writer.write(f"<li><details style='margin-left: 2em'><summary style='margin-left: -2em'>{cls.replace('yago:','y:')}: {str(classStats.get(cls,0))}</summary><ul>\n")
    for subclass in yagoTaxonomyDown.get(cls, []):
        _printTaxonomy(writer, subclass)
    writer.write("</ul></details>\n")

def printTaxonomy(file):
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
        _printTaxonomy(writer)
        writer.write("</ul></body>\n</html>")

##########################################################################
#             Top-level taxonomy as HTML
##########################################################################
 
def printUpperTaxonomy(file):
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

with TsvUtils.Timer("Step 06: Collecting YAGO statistics"):

    # Load YAGO schema
    yagoSchema = YagoSchema(FOLDER+"01-yago-final-schema.ttl")

    # Load YAGO taxonomy
    yagoTaxonomyDown=defaultdict(set)
    yagoTaxonomyUp=defaultdict(set)
    for triple in TsvUtils.tsvTuples(FOLDER+"05-yago-final-taxonomy.tsv", "  Loading YAGO taxonomy"):
        if len(triple)>3:
            yagoTaxonomyUp[triple[0]].add(triple[2])
            yagoTaxonomyDown[triple[2]].add(triple[0])

    # Initialize counters
    predicateStats=defaultdict(int)
    classStats=defaultdict(int)
    samples=[]
    entities=0
    totalPathsToRoot=0
    totalClassesPerInstance=0
    humanReadableNames=0

    # Initialize predicateStats with predicates from schema, same for classes
    for yagoProperty in yagoSchema.properties:
        predicateStats[yagoProperty]=0
    predicateStats[Prefixes.rdfType]=0    
    for yagoClass in yagoSchema.classes:
        classStats[yagoClass]=0
     
    genericInstancesCount=0
    
    # Run through the facts
    for entityFacts in itertools.chain(TurtleUtils.tsvEntities(FOLDER+"05-yago-final-wikipedia.tsv", "  Parsing YAGO Wikipedia"), TurtleUtils.tsvEntities(FOLDER+"05-yago-final-beyond-wikipedia.tsv", "  Parsing YAGO beyond Wikipedia")):
        mainEntity=entityFacts.mainSubject()
        if (mainEntity, Prefixes.rdfType, Prefixes.rdfsClass) in entityFacts:
            continue
        for p in entityFacts.predicatesOf(mainEntity):
            predicateStats[p]+=1
        if mainEntity.endswith("_generic_instance"):
            genericInstancesCount+=1                
        entities+=1
        if not re.match(r"yago:Q[0-9]+", mainEntity):
            humanReadableNames+=1
        superClasses=set()
        pathsToRoot=[0]
        for c in entityFacts.objectsOf(mainEntity, Prefixes.rdfType):
            getSuperClasses(c, superClasses, yagoTaxonomyUp, pathsToRoot)
        for c in superClasses:
            classStats[c]+=1 
        totalClassesPerInstance+=len(superClasses)   
        totalPathsToRoot+=pathsToRoot[0]      
        if (len(samples)<100 or (len(samples)==100 and random.random()<0.01)):
            for c in superClasses:
                entityFacts.add((mainEntity, 'rdf:type', c))
            if len(samples)<100:
                samples.append(entityFacts)
            else:    
                samples[int(random.random()*99)]=entityFacts        
            
    print("  Writing out sample entities... ",end="",flush=True)    
    with open(FOLDER+"06-sample-entities.ttl", "wt", encoding="UTF-8") as sampleFile:
        for sample in samples:
            sample.printToWriter(sampleFile)
    print("done")

    metaFacts=0
    for triple in TsvUtils.tsvTuples(FOLDER+"05-yago-final-meta.tsv", "  Counting meta facts"):
        metaFacts += 1
    
    print("  Computing dump size... ",end="",flush=True)    
    dumpSize=0
    for f in glob.glob(FOLDER+"*final*.tsv"):
        dumpSize+=os.path.getsize(f)
    print("done")
    
    print("  Writing out statistics... ",end="",flush=True)    
    with open(FOLDER+"06-statistics.txt", "wt", encoding="UTF-8") as writer:
        writer.write("YAGO 4.5 statistics\n\n")
        writer.write("Dump size: "+str(dumpSize/1024/1024/1024)+" GB\n\n")
        writer.write("Total number of entities: "+str(entities)+"\n\n")
        writer.write("  ... of which generic: "+str(genericInstancesCount)+"\n\n")
        writer.write("Total number of classes: "+str(len(yagoTaxonomyUp))+"\n\n")
        writer.write("Disjointness statements: "+str(sum(len(yagoClass.disjointWith) for yagoClass in yagoSchema.classes.values()))+"\n\n")
        writer.write("Avg number of paths to root: "+str(totalPathsToRoot/entities)+"\n\n")        
        writer.write("Avg number of classes per instance: "+str(totalClassesPerInstance/entities)+"\n\n")        
        writer.write("Human-readable names: "+str(humanReadableNames*100.0/entities)+"%\n\n")
        writer.write("Total number of facts (excluding labels etc.): "+str(sum([predicateStats[p] for p in predicateStats if p not in excludePredicates]))+"\n\n")
        writer.write("Avg number of facts (excluding labels etc.) per entity: "+str(sum([predicateStats[p] for p in predicateStats if p not in excludePredicates])/entities)+"\n\n")
        writer.write("Total number of meta facts: "+str(metaFacts)+"\n\n")
        writer.write("Total number of predicates: "+str(len(predicateStats))+"\n\n")
        writer.write("Predicates:\n")
        for pred in sorted(predicateStats.items(), key=lambda x:-x[1]):
            writer.write("  "+pred[0]+": "+str(pred[1])+"\n")        
    print("done")
     
    print("  Writing out taxonomy... ",end="",flush=True)    
    printTaxonomy(FOLDER+"06-taxonomy.html")
    printUpperTaxonomy(FOLDER+"06-upper-taxonomy.html")
    print("done")
    
if TEST:
    Evaluator.compare(FOLDER+"06-statistics.txt", FOLDER+"06-statistics-gold.txt")
    Evaluator.compare(FOLDER+"06-taxonomy.html", FOLDER+"06-taxonomy-gold.html")
    Evaluator.compare(FOLDER+"06-upper-taxonomy.html", FOLDER+"06-upper-taxonomy-gold.html")