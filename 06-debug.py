"""
Produces statistics about YAGO entities and predicates, and extracts samples

(c) 2022 Fabian M. Suchanek

Input:
- 01-yago-final-schema.ttl
- 05-yago-final-beyond-wikipedia.tsv
- 05-yago-final-wikipedia.tsv
- 05-yago-final-taxonomy.tsv

Output:
- 06-statistics.txt
- 06-taxonomy.html
- 06-sample-entities.ttl

Algorithm:
- load taxonomy
- run through yago-final-full
  - update statistics
  - sample entities
   
"""

TEST=False
FOLDER="test-data/06-debug/" if TEST else "yago-data/"

##########################################################################
#             Booting
##########################################################################

import sys
import evaluator
import itertools
import TurtleUtils
import TsvUtils
import random
import Prefixes
from collections import defaultdict

def getSuperClasses(cls, classes, yagoTaxonomyUp):
    """Adds all superclasses of a class <cls> (including <cls>) to the set <classes>"""
    classes.add(cls)
    # Make a check before because it's a defaultdict,
    # which would create cls if it's not there
    if cls in yagoTaxonomyUp:
        for sc in yagoTaxonomyUp[cls]:
            getSuperClasses(sc, classes, yagoTaxonomyUp)

def printTaxonomy(writer, yagoTaxonomyDown, classStats, cls=Prefixes.schemaThing):
    """ Prints the taxonomy to the writer. <yagoTaxonomyDown> maps a class to the set of sub-classes. <classStats> maps a class to its number of instances. <cls> is the class to start with, i.e., the top-level class. """
    if cls not in yagoTaxonomyDown:
        writer.write(f"<li>{cls.replace('yago:','y:')}: {str(classStats.get(cls,0))}\n")
        return
    writer.write(f"<li><details><summary>{cls.replace('yago:','y:')}: {str(classStats.get(cls,0))}</summary><ul>\n")
    for subclass in yagoTaxonomyDown.get(cls, []):
        printTaxonomy(writer, yagoTaxonomyDown, classStats, subclass)
    writer.write("</ul></details>\n")
        
##########################################################################
#             Main
##########################################################################

with TsvUtils.Timer("Step 06: Collecting YAGO statistics"):

    # Load YAGO schema
    yagoSchema = TurtleUtils.Graph()
    yagoSchema.loadTurtleFile(FOLDER+"01-yago-final-schema.ttl", "  Loading YAGO schema")

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

    # Initialize predicateStats with predicates from schema, same for classes
    for s, p, o in yagoSchema.triplesWithPredicate("sh:path"):
        predicateStats[o]=0
    for s, p, o in yagoSchema.triplesWithPredicate("rdfs:subClassOf"):
        classStats[s]=0
            
    # Run through the facts
    for entityFacts in itertools.chain(TurtleUtils.tsvEntities(FOLDER+"05-yago-final-wikipedia.tsv", "  Parsing YAGO Wikipedia"), TurtleUtils.tsvEntities(FOLDER+"05-yago-final-beyond-wikipedia.tsv", "  Parsing YAGO beyond Wikipedia")):
        classes=set()
        subject=None
        for s, p, o in entityFacts:
            predicateStats[p]+=1
            if p=='rdf:type':
                classes.add(o)
                subject=s
        entities+=1
        superClasses=set()
        for c in classes:
            getSuperClasses(c, superClasses, yagoTaxonomyUp)
        for c in superClasses:
            classStats[c]+=1   
        if subject and (len(samples)<100 or (len(samples)==100 and random.random()<0.01)):
            for c in superClasses:
                entityFacts.add((subject, 'rdf:type', c))
            if len(samples)<100:
                samples.append(entityFacts)
            else:    
                samples[int(random.random()*99)]=entityFacts        
            
    print("  Writing out sample entities... ",end="",flush=True)    
    with open(FOLDER+"06-sample-entities.ttl", "wt", encoding="UTF-8") as sampleFile:
        for sample in samples:
            sample.printToWriter(sampleFile)
    print("done")

    print("  Writing out statistics... ",end="",flush=True)    
    with open(FOLDER+"06-statistics.txt", "wt", encoding="UTF-8") as writer:
        writer.write("YAGO 4.1 statistics\n\n")
        writer.write("Total number of entities: "+str(entities)+"\n\n")
        writer.write("Predicates:\n")
        for pred in sorted(predicateStats.items(), key=lambda x:-x[1]):
            writer.write("  "+pred[0]+": "+str(pred[1])+"\n")        
    print("done")
       
    print("  Writing out taxonomy... ",end="",flush=True)    
    with open(FOLDER+"06-taxonomy.html", "wt", encoding="UTF-8") as writer:
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
        printTaxonomy(writer, yagoTaxonomyDown, classStats)
        writer.write("</ul></body>\n</html>")
    print("done")
    
if TEST:
    evaluator.compare(FOLDER+"06-statistics.txt", FOLDER+"06-statistics-gold.txt")
    evaluator.compare(FOLDER+"06-taxonomy.html", FOLDER+"06-taxonomy-gold.html")