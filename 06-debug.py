"""
Produces statistics about YAGO entities and predicates, and extracts samples

(c) 2022 Fabian M. Suchanek

Input:
- 01-yago-schema.ttl
- 05-yago-final-full.tsv
- 05-yago-final-taxonomy.tsv

Output:
- 06-statistics.tsv
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
import TurtleUtils
import TsvUtils
import random
from collections import defaultdict

def getSuperClasses(cls, classes, yagoTaxonomyUp):
    """Adds all superclasses of a class <cls> (including <cls>) to the set <classes>"""
    classes.add(cls)
    # Make a check before because it's a defaultdict,
    # which would create cls if it's not there
    if cls in yagoTaxonomyUp:
        for sc in yagoTaxonomyUp[cls]:
            getSuperClasses(sc, classes, yagoTaxonomyUp)


##########################################################################
#             Main
##########################################################################

print("Collecting YAGO statistics...")

# Load YAGO schema
yagoSchema = TurtleUtils.Graph()
yagoSchema.loadTurtleFile(FOLDER+"01-yago-schema.ttl", "  Loading YAGO schema")

# Load YAGO taxonomy
yagoTaxonomyUp=defaultdict(set)
for triple in TsvUtils.tsvTuples(FOLDER+"05-yago-final-taxonomy.tsv", "  Loading YAGO taxonomy"):
    if len(triple)>3:
        yagoTaxonomyUp[triple[0]].add(triple[2])

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
for entityFacts in TurtleUtils.tsvEntities(FOLDER+"05-yago-final-full.tsv", "  Parsing YAGO"):
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
with TsvUtils.TsvFileWriter(FOLDER+"06-statistics.tsv") as writer:
    writer.write("yago:YAGO","yago:hasCount", str(entities))
    writer.write("\n#Predicates")
    for pred in sorted(predicateStats.items(), key=lambda x:-x[1]):
        writer.write(pred[0], "yago:hasCount", str(pred[1]))
    writer.write("\n#Classes")
    for pred in sorted(classStats.items(), key=lambda x:-x[1]):
        writer.write(pred[0], "yago:hasCount", str(pred[1]))            
print("done")
        
print("done")

if TEST:
    evaluator.compare(FOLDER+"06-statistics.tsv")