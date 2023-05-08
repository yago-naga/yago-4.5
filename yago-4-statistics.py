"""
Produces statistics about YAGO 4 entities and predicates
   
"""

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

###########################################################################
#           Counting and removing shortcuts
###########################################################################

yagoTaxonomyUp=defaultdict(set)

def removeShortcutParentsOf(startClass, currentClass):
    """ Removes direct superclasses of startClass that are equal to currentClass or its super-classes """
    if currentClass in yagoTaxonomyUp.get(startClass,[]):
        yagoTaxonomyUp[startClass].remove(currentClass)
        # print("   Removing",startClass,"to",currentClass)
        if len(yagoTaxonomyUp[startClass])==1:
            return        
    for s in yagoTaxonomyUp.get(currentClass,[]):
        removeShortcutParentsOf(startClass, s)
        
def removeShortcuts():
    """ Removes all shortcut links in the YAGO taxonomy """
    for c in list(yagoTaxonomyUp):
        if len(yagoTaxonomyUp.get(c,[]))>1:
            for s in list(yagoTaxonomyUp.get(c,[])):
                for ss in yagoTaxonomyUp.get(s,[]):
                    removeShortcutParentsOf(c, ss)
 
###########################################################################
#           Retrieving superclasses
###########################################################################

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

##########################################################################
#             Main
##########################################################################

with TsvUtils.Timer("Collecting YAGO 4 statistics"):

    for triple in TsvUtils.tsvTuples("../yago-4/classes.nt", "  Loading YAGO 4 taxonomy"):
        if len(triple)>3 and triple[1]=="<http://www.w3.org/2000/01/rdf-schema#subClassOf>":
            yagoTaxonomyUp[triple[0]].add(triple[2])
    
    before=sum(len(yagoTaxonomyUp[s]) for s in yagoTaxonomyUp)
    print("  Taxonomic links before shortcut removal:", before)
    removeShortcuts()
    after=sum(len(yagoTaxonomyUp[s]) for s in yagoTaxonomyUp)
    print("  Taxonomic links after shortcut removal:", after)
    print("  Links removed:", before-after)
    
    directClasses=set()
    currentSubject=""
    totalEntities=0
    totalClassesPerInstance=0
    totalPathsToRoot=0
    for triple in TsvUtils.tsvTuples("../yago-4/full-types-sorted.nt", "  Running through YAGO 4 types"):
        if triple[1]!="<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>":
            continue
        if triple[0]==currentSubject:
            directClasses.add(triple[2])
            continue
        totalEntities+=1
        superClasses=set()
        for c in classes:
            getSuperClasses(c, superClasses, yagoTaxonomyUp, pathsToRoot)
        totalClassesPerInstance+=len(superClasses)   
        totalPathsToRoot+=pathsToRoot[0]  
        directClasses=set()
        currentSubject=triple[0]
        directClasses.add(triple[2])
        
    print("  Total entities:", totalEntities)
    print("  Avg paths to root:", totalPathsToRoot/totalEntities)
    print("  Avg classes per instance:", totalClassesPerInstance/totalEntities)