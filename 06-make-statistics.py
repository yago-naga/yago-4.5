"""
Produces statistics about YAGO entities and predicates, and extracts samples

CC-BY 2022 Fabian M. Suchanek

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

TEST=False
FOLDER="test-data/06-make-statistics/" if TEST else "yago-data/"

##########################################################################
#             Booting
##########################################################################

import sys
import glob
import re
import evaluator
import itertools
import TurtleUtils
import TsvUtils
import random
import os
import Prefixes
from collections import defaultdict

# Predicates that are excluded for fact counting
excludePredicates=["rdfs:label", "rdfs:comment", "rdf:type", "schema:mainEntityOfPage", "owl:sameAs", "schema:alternateName"]

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

def printTaxonomy2(writer, cls=Prefixes.schemaThing):
    """ Prints the taxonomy to the writer. <cls> is the class to start with, i.e., the top-level class. """
    if cls not in yagoTaxonomyDown:
        writer.write(f"<li>{cls.replace('yago:','y:')}: {str(classStats.get(cls,0))}\n")
        return
    writer.write(f"<li><details style='margin-left: 2em'><summary style='margin-left: -2em'>{cls.replace('yago:','y:')}: {str(classStats.get(cls,0))}</summary><ul>\n")
    for subclass in yagoTaxonomyDown.get(cls, []):
        printTaxonomy2(writer, subclass)
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
        printTaxonomy2(writer)
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
        def add_node(cls):
            if not yagoSchema.objects(cls):
                return
            writer.write(f"<li><details style='margin-left: 2em'><summary style='font-weight:bold; margin-left: -2em'>{cls}</summary><details style='margin-left: 2em'><summary style='margin-left: -2em'>Outgoing properties</summary><ul style='list-style-type: none'>\n")
            for blank in sorted(yagoSchema.objects(cls,Prefixes.shaclProperty), key=lambda b: yagoSchema.objects(b, Prefixes.shaclPath)):
                writer.write(f'<li>- {yagoSchema.objects(blank, Prefixes.shaclPath)[0]}')
                if yagoSchema.objects(blank, Prefixes.shaclNode):
                    ran=yagoSchema.objects(blank, Prefixes.shaclNode)[0]
                elif yagoSchema.objects(blank, Prefixes.shaclOr):
                    ran=", ".join([target for el in yagoSchema.getList(yagoSchema.objects(blank, Prefixes.shaclOr)[0]) for target in yagoSchema.objects(el, Prefixes.shaclNode) + yagoSchema.objects(el, Prefixes.shaclDatatype)])
                elif yagoSchema.objects(blank, Prefixes.shaclDatatype):
                    ran=yagoSchema.objects(blank, Prefixes.shaclDatatype)[0]
                if ran:
                    writer.write(" &rarr;")
                    maxCount=yagoSchema.objects(blank, Prefixes.shaclMaxCount)
                    if maxCount:
                        writer.write("<sup>"+maxCount[0]+"</sup>")
                    elif yagoSchema.objects(blank, Prefixes.shaclUniqueLang):
                        writer.write("<sup>1 per language</sup>")
                    writer.write(" "+ran+"\n")    
            writer.write("</ul></details>\n<details style='margin-left: 2em'><summary style='margin-left: -2em'>Incoming properties</summary><ul style='list-style-type: none'>\n")
            for blank in sorted(yagoSchema.subjects(Prefixes.shaclNode, cls)):
                p=yagoSchema.objects(blank, Prefixes.shaclPath)
                c=yagoSchema.subjects(Prefixes.shaclProperty,blank)
                if p and c:
                    writer.write(f'<li>- ({c[0]}) {p[0]}')
            writer.write("</ul></details><details style='margin-left: 2em'><summary style='margin-left: -2em'>Subclasses</summary><ul style='list-style-type: none'>\n")
            for subclass in sorted(yagoTaxonomyDown.get(cls, [])):
                add_node(subclass)
            writer.write("</ul></details></details>\n")
        add_node("schema:Thing")
        writer.write("</ul>")
 
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
    totalPathsToRoot=0
    totalClassesPerInstance=0
    humanReadableNames=0

    # Initialize predicateStats with predicates from schema, same for classes
    for s, p, o in yagoSchema.triplesWithPredicate(Prefixes.shaclPath):
        predicateStats[o]=0
    for s, p, o in yagoSchema.triplesWithPredicate("rdfs:subClassOf"):
        classStats[s]=0
     
    genericInstancesCount=0
    
    # Run through the facts
    for entityFacts in itertools.chain(TurtleUtils.tsvEntities(FOLDER+"05-yago-final-wikipedia.tsv", "  Parsing YAGO Wikipedia"), TurtleUtils.tsvEntities(FOLDER+"05-yago-final-beyond-wikipedia.tsv", "  Parsing YAGO beyond Wikipedia")):
        classes=set()
        subject=None
        for s, p, o in entityFacts:
            predicateStats[p]+=1
            if p=='rdf:type':
                classes.add(o)
                if s.endswith("_generic_instance"):
                    genericInstancesCount+=1
                subject=s
        if subject is None or "rdfs:Class" in classes:
            continue
        entities+=1
        superClasses=set()
        pathsToRoot=[0]
        if not re.match(r"yago:Q[0-9]+", subject):
            humanReadableNames+=1
        for c in classes:
            getSuperClasses(c, superClasses, yagoTaxonomyUp, pathsToRoot)
        for c in superClasses:
            classStats[c]+=1 
        totalClassesPerInstance+=len(superClasses)   
        totalPathsToRoot+=pathsToRoot[0]      
        if (len(samples)<100 or (len(samples)==100 and random.random()<0.01)):
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
        writer.write("Disjointness statements: "+str(len(yagoSchema.triplesWithPredicate(Prefixes.owlDisjointWith)))+"\n\n")
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
    evaluator.compare(FOLDER+"06-statistics.txt", FOLDER+"06-statistics-gold.txt")
    evaluator.compare(FOLDER+"06-taxonomy.html", FOLDER+"06-taxonomy-gold.html")
    evaluator.compare(FOLDER+"06-upper-taxonomy.html", FOLDER+"06-upper-taxonomy-gold.html")