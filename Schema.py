"""
Loading and handling the YAGO schema

CC-BY 2025 Fabian M. Suchanek
"""

import sys
import re
import TurtleUtils
import Prefixes
import itertools

def message(*mess):
    """ Prints a message """
    for m in mess:
        sys.stdout.buffer.write(str(m).encode('utf8'))
        sys.stdout.buffer.write(b" ")
    sys.stdout.buffer.write(b"\n")


def warning(*mess):
    """ Prints a warning """
    sys.stdout.buffer.write(b"    Warning: ")
    message(*mess)

def info(*mess):
    """ Prints an info """
    sys.stdout.buffer.write(b"    Info: ")
    message(*mess)

def getFirst(myList):
    """ Returns the first element of an iterable or none """    
    for o in myList:
        return o
    return None
    
class YagoObject:
    """ Common super class for YAGO properties and YAGO classes"""
    def __init__(self, identifier):
        self.identifier = identifier
        self.labels = set()
        self.comments = set()
    def __eq__(self, other):
        try:
            return other and other.identifier==self.identifier
        except:
            return False
    def __hash__(self):
        try:
            return hash(self.identifier)
        except:
            return 0
    def __lt__(self, other):
        try:
            return self.identifier<other.identifier
        except:
            return False
    def check(self):
        """ Performs simple checks """
        if not TurtleUtils.isEntityWithPrefix(self.identifier):
            warning("YAGO object",self,"has an invalid identifier")
        # If we do not have a label, invent one by splitting the identifier by Camel Case.
        # We also get labels from Wikidata, but YAGO-tiny will not have them. By putting them here, we make them part of the schema and YAGO-tiny gets them
        if not self.labels:
            self.labels.add('"'+re.sub("([a-z])([A-Z])","\\1 \\2",stripPrefix(self.identifier))+'"@en')        
        for s in itertools.chain(self.labels,self.comments):
            literal, _, lang, _ = TurtleUtils.splitLiteral(s)
            if not literal:
                warning("YAGO object",self,"has an invalid label or comment:",s)
            if not lang:
                warning("YAGO object",self,"has a label or comment without language tag:",s)
        if len(self.comments)>1:
           warning("YAGO object",self,"has more than one comment:", ", ".join(self.comments))
        if len(self.labels)>1:
           warning("YAGO object",self,"has more than one label:", ", ".join(self.labels))
            
def stripPrefix(identifier):
    """ Removes the xyz: prefix"""
    return identifier[identifier.find(':')+1:]

def maxValue(val, values):
    """ Returns the maximum value of the given ones or None"""
    for v in values:
        if v is None:
            continue
        try:
            v=int(v)
            if val==None or v>val:
                val=v
        except:
            warning("Invalid numerical value:",v)
    return val

def minValue(val, values):
    """ Returns the minimum value of the given ones or None"""
    for v in values:
        if v is None:
            continue
        try:
            v=int(v)
            if val==None or v<val:
                val=v
        except:
            warning("Invalid numerical value:",v)            
    return val

class YagoProperty(YagoObject):
    """ Represents a YAGO property with its attributes"""
    def __init__(self, name):
        super().__init__(name)
        self.objectTypes=set()
        self.subjectTypes=set()
        self.wikidataProperties=set()
        self.maxCount=None
        self.minCount=None
        self.minInclusive=None
        self.maxInclusive=None        
        self.uniqueLang=False
        self.pattern=None  
        self.isDatatype=None
    
    def check(self):
        """ Performs simple checks """
        super().check()
        if not self.objectTypes:
            warning("Property",self,"has no object types")
        if not self.subjectTypes:
            warning("Property",self,"has no subject types")
        if not self.wikidataProperties:
            warning("Property",self,"has no Wikidata properties")
        if self.maxCount is not None and self.maxCount<1:
            warning("Property",self,"has an invalid max count of",self.maxCount)
        if self.minCount is not None and self.minCount<1:
            warning("Property",self,"has an invalid min count of",self.minCount)
        if self.maxInclusive is not None and self.minInclusive is not None and self.minInclusive>=self.maxInclusive:
            warning("Property",self,"has large min inclusive than max inclusive",self.minInclusive, self.maxInclusive)
        if self.pattern and not TurtleUtils.isRegex(self.pattern):
            warning("Property",self,"has an invalid pattern of",self.pattern)
            
    def __str__(self):
        return self.identifier
    
    def schemaIdentifier(self):
        """ Returns a blank node name for this property """
        return "ys:"+stripPrefix(self.identifier)+"_property"
        
    def writeTo(self, out):
        """ Pretty prints property to output stream """
        out.write(self.schemaIdentifier()+"\n")
        out.write("\t\tsh:path "+self.identifier+" ;\n")
        if self.labels:
            out.write("\t\trdfs:label "+", ".join(c for c in self.labels)+" ;\n")        
        if self.comments:
            out.write("\t\trdfs:comment "+", ".join(c for c in self.comments)+" ;\n")      
        if self.uniqueLang:
            out.write("\t\tsh:uniqueLang true ;\n")
        if self.maxCount is not None:
            out.write("\t\tsh:maxCount "+str(self.maxCount)+" ;\n")
        if self.minCount is not None:
            out.write("\t\tsh:minCount "+str(self.minCount)+" ;\n")
        if self.maxInclusive is not None:
            out.write("\t\tsh:maxInclusive "+str(self.maxInclusive)+" ;\n")
        if self.minInclusive is not None:
            out.write("\t\tsh:minInclusive "+str(self.minInclusive)+" ;\n")
        if self.pattern:
            out.write("\t\tsh:pattern \""+self.pattern.replace("\\","\\\\")+"\" ;\n")
        out.write("\t\tys:fromProperty "+", ".join(c for c in self.wikidataProperties)+" ;\n")
        if len(self.objectTypes)>1:
            out.write("\t\tsh:or ([ ")            
            out.write(" ][ ".join("sh:datatype "+p if self.isDatatype else "sh:class "+p for p in self.objectTypes))
            out.write("]).\n\n")
        else:
            out.write("".join("\t\tsh:datatype "+p if self.isDatatype else "\t\tsh:class "+p for p in self.objectTypes)+" .\n\n")  
        if self.labels:
            out.write(self.identifier+"\trdfs:label "+", ".join(c for c in self.labels)+" .\n\n")        
        if self.comments:
            out.write(self.identifier+"\trdfs:comment "+", ".join(c for c in self.comments)+" .\n\n")
    
    def addObjectTypes(self, types, isDatatype):
        """ Adds all the object types"""
        if not types:
            return
        if self.isDatatype is not None and self.isDatatype!=isDatatype:
            warning("Property",self.identifier,"has both datatype and class objects:", self.isDatatype, isDatatype)
        self.isDatatype=isDatatype
        self.objectTypes.update(types)
        
    def updateFromShacl(self, shaclProperty, entityGraph):
        """ Adds what the SHACL property says to this YAGO property """
        
        # Object types
        self.addObjectTypes(entityGraph.objectsOf(shaclProperty,Prefixes.shaclClass), False)
        self.addObjectTypes(entityGraph.objectsOf(shaclProperty,Prefixes.shaclDatatype), True)
        for disjunctionNode in entityGraph.objectsOf(shaclProperty,Prefixes.shaclOr):
            self.addObjectTypes([typ for anon in entityGraph.getList(disjunctionNode) for typ in entityGraph.objectsOf(anon,Prefixes.shaclClass)], False)
            self.addObjectTypes([typ for anon in entityGraph.getList(disjunctionNode) for typ in entityGraph.objectsOf(anon,Prefixes.shaclDatatype)], True)
        
        # Labels and comments
        self.labels.update(entityGraph.objectsOf(shaclProperty,Prefixes.rdfsLabel))
        self.comments.update(entityGraph.objectsOf(shaclProperty,Prefixes.rdfsComment))
        
        # Wikidata mappings        
        self.wikidataProperties.update(entityGraph.objectsOf(shaclProperty,Prefixes.fromProperty))
        
        # Unique language and maxCounts
        self.uniqueLang=self.uniqueLang or (shaclProperty,Prefixes.shaclUniqueLang,"true") in entityGraph
        self.maxCount=maxValue(self.maxCount,entityGraph.objectsOf(shaclProperty,Prefixes.shaclMaxCount))
        self.minCount=minValue(self.minCount,entityGraph.objectsOf(shaclProperty,Prefixes.shaclMinCount))
        self.maxInclusive=maxValue(self.maxInclusive,entityGraph.objectsOf(shaclProperty,Prefixes.shaclMaxInclusive))
        self.minInclusive=minValue(self.minInclusive,entityGraph.objectsOf(shaclProperty,Prefixes.shaclMinInclusive))
                
        # Patterns
        patterns=entityGraph.objectsOf(shaclProperty,Prefixes.shaclPattern)
        if len(patterns)>1:
            warning("Property", self,"has more than one pattern:",patterns)
        if len(patterns)>0:
            compileMe=TurtleUtils.splitLiteral(getFirst(patterns))[0].replace("\\\\","\\")
            if self.pattern and self.pattern!=compileMe:
               warning("Property",self,"has different patterns:",self.pattern,"and",compileMe)
            self.pattern=compileMe
                
class YagoClass(YagoObject):
    """ A class of YAGO """
    
    def __init__(self, identifier):
        super().__init__(identifier)
        self.fromClasses=set()
        self.disjointWith=set()
        self.properties=set()
        self.superClasses=set()
    
    def check(self):
        """ Performs some simple checks"""
        super().check()
        # If we do not have a label, and won't get one from Wikidata, invent one by splitting the identifier by Camel Case
        if not self.labels and not self.fromClasses:
            self.labels.add('"'+re.sub("([a-z])([A-Z])","\\1 \\2",stripPrefix(self.identifier))+'"@en')        
        if self.comments and self.fromClasses:
            warning("Class",self,"has a comment although it will inherit one from Wikidata. Remove it.")
        if not self.superClasses and self.identifier!=Prefixes.schemaThing and not self.identifier.startswith("rdf:") and not self.identifier.startswith("rdfs:"):
            warning("Class",self,"does not have a super class")
        for p in self.properties:
            queue=[s for s in self.superClasses]
            for s in queue:
                if p in s.properties:
                    warning("Subclass",self.identifier,"redefines property",p,"of superclass",s)
                    queue.extend(s.superClasses)
                    
    def __str__(self):
        return self.identifier
        
    def writeTo(self,out):
        """ Writes the class to a Turtle file """
        out.write(self.identifier+" a sh:NodeShape ;\n")
        if self.superClasses:
            out.write("\t"+Prefixes.rdfsSubClassOf+" "+", ".join(c.identifier for c in self.superClasses)+" ;\n")
        if self.disjointWith:
            out.write("\t"+Prefixes.owlDisjointWith+" "+", ".join(c.identifier for c in self.disjointWith)+" ;\n")
        if self.labels:
            out.write("\t"+Prefixes.rdfsLabel+" "+", ".join(c for c in self.labels)+" ;\n")        
        if self.comments:
            out.write("\t"+Prefixes.rdfsComment+" "+", ".join(c for c in self.comments)+" ;\n")        
        if self.fromClasses:
            out.write("\t"+Prefixes.fromClass+" "+", ".join(c for c in self.fromClasses)+" ;\n" )
        if self.properties:
            out.write("\tsh:property "+", ".join(p.schemaIdentifier() for p in self.properties)+" ;\n")
        out.write("\ta rdfs:Class .\n\n")
        
    def updateFromShacl(self, entityGraph, yagoSchema):
        """ Adds the properties given by the SHACL property to this class."""
        
        # Labels and comments
        self.labels.update(entityGraph.objectsOf(self.identifier,Prefixes.rdfsLabel))
        self.comments.update(entityGraph.objectsOf(self.identifier,Prefixes.rdfsComment))
        
        # Corresponding Wikidata classes
        self.fromClasses.update(entityGraph.objectsOf(self.identifier, Prefixes.fromClass))
        
        # Disjoint classes
        for c in entityGraph.objectsOf(self.identifier, Prefixes.owlDisjointWith):
            disjointClass=yagoSchema.getClass(c)
            self.disjointWith.add(disjointClass)
            disjointClass.disjointWith.add(self)
        
        # Superclasses
        self.superClasses.update(yagoSchema.getClass(c) for c in entityGraph.objectsOf(self.identifier, Prefixes.rdfsSubClassOf))
        
        # Properties
        for shaclProperty in entityGraph.objectsOf(self.identifier, Prefixes.shaclProperty):
            # Property name            
            propertyNames=entityGraph.objectsOf(shaclProperty,Prefixes.shaclPath)
            if len(propertyNames)>1:
                warning("Property",shaclProperty,"has non-unique path",propertyNames)
            elif len(propertyNames)==0:
                warning("Property",shaclProperty,"has no path")
                propertyNames=["NOPATH"]
            propertyName=getFirst(propertyNames) 
            yagoProperty=yagoSchema.getProperty(propertyName)
            yagoProperty.subjectTypes.add(self.identifier)
            yagoProperty.updateFromShacl(shaclProperty, entityGraph)
            self.properties.add(yagoProperty)

PREDEFINED_LABELS={
"owl:disjointWith": '"is disjoint with"@en',
"rdf:first": '"first element of a list"@en',
"rdf:rest": '"next element of a list"@en',
"rdfs:subClassOf": '"is subclass of"@en',
"sh:class": '"has range"@en',
"sh:datatype": '"has datatype"@en',
"sh:maxCount": '"has maxcount"@en',
"sh:maxInclusive": '"is max inclusive of"@en',
"sh:minCount": '"has min count"@en',
"sh:minInclusive": '"is min inclusive of"@en',
"sh:or": '"one of"@en',
"sh:path": '"concerns"@en',
"sh:pattern": '"has pattern"@en',
"sh:property": '"has property"@en',
"sh:NodeShape": '"SHACL node shape"@en',
"sh:uniqueLang": '"has unique language"@en',
"ys:fromClass": '"derives from Wikidata class"@en',
"ys:fromProperty": '"derives from Wikidata property"@en',
"rdfs:subPropertyOf": '"is subproperty of"@en'
}

class YagoSchema(object):
    """ The YAGO schema """
    
    def __init__(self, file=None, verbose=True):        
        self.properties={}
        self.wikidataProperties={}
        self.wikidataClasses={}
        self.classes={}
        if file:
            self.addTurtleFile(file, verbose)
    
    def getClass(self, classIdentifier):
        """ Returns a class of that name (creating it if needed)"""
        if not isinstance(classIdentifier,str):
           warning(classIdentifier,"is not a string, but a",type(classIdentifier))
        if classIdentifier not in self.classes:
            self.classes[classIdentifier]=YagoClass(classIdentifier)
        return self.classes[classIdentifier]
    
    def getProperty(self, propertyIdentifier):
        """ Returns a property of that name (creating it if needed)"""
        if propertyIdentifier not in self.properties:
            self.properties[propertyIdentifier]=YagoProperty(propertyIdentifier)
        return self.properties[propertyIdentifier]
        
    def addClass(self, classIdentifier, entityGraph):
        """ Adds a class of the given name from the graph to the schema """        
        yagoClass=self.getClass(classIdentifier)
        yagoClass.updateFromShacl(entityGraph, self)
        # Update Wikidata property mapping
        for yagoProperty in yagoClass.properties:
            for w in yagoProperty.wikidataProperties:
                if w not in self.wikidataProperties:
                    self.wikidataProperties[w]=set()
                self.wikidataProperties[w].add(yagoProperty)
        for wikidataClass in yagoClass.fromClasses:
            if wikidataClass in self.wikidataClasses:
                warning("Wikidata class", wikidataClass, "is mapped to both",yagoClass,"and",self.wikidataClasses[wikidataClass])
            self.wikidataClasses[wikidataClass]=yagoClass
            
    def addTurtleFile(self, yagoSchemaFile, verbose=True):
        """ Loads a Turtle file """
        # Load schema file
        if verbose:
            print("  Loading YAGO Schema...")
            print("    Input file:",yagoSchemaFile)

        entityGraph=TurtleUtils.Graph()
        entityGraph.loadTurtleFile(yagoSchemaFile)
        for (s,p,o) in entityGraph:
            if p==Prefixes.rdfType and o==Prefixes.shaclNodeShape:
                self.addClass(s, entityGraph)
        
        self.check()
        
        if verbose:
            print("    Info:", len(self.properties),"properties")
            print("    Info:", len(self.classes),"classes")
            print("  done")
        
    def __str__(self):
        return("\n".join(str(s) for s in self.properties.values()))        
        
    def writeTo(self,out):
        """ Writes the schema to the stream """
        for clss in self.classes.values():
            clss.writeTo(out)
        for prop in self.properties.values():
            prop.writeTo(out)
        out.write("sh:NodeShape rdf:type rdfs:Class .\n")    
        # Make sure all properties have a label, even the RDF ones    
        for prop in PREDEFINED_LABELS:
            if prop not in self.properties:
                out.write(prop+" rdfs:label "+PREDEFINED_LABELS[prop]+" .\n")
          
    def writeToFile(self,file):
        """ Writes the schema to a file"""
        print("Wruting to",file)
        with open(file, "wt", encoding="utf-8") as out:
            for p in Prefixes.prefixes:
                out.write("@prefix "+p+": <"+Prefixes.prefixes[p]+"> .\n")
            out.write("\n")    
            self.writeTo(out)
            
    def check(self):
        """ Performs simple checks """
        for c in self.classes.values():
            c.check()
        for p in self.properties.values():
            p.check()
        for c in self.classes.values():
            if not c.fromClasses and not c.identifier.startswith("rdf") and not any(c in c2.superClasses for c2 in self.classes.values()):
               print("    Warning: Class",c,"is not mapped to Wikidata")
            for c2 in c.disjointWith:
                if c2.identifier not in self.classes:
                    print("    Warning: Undeclared disjoint class",c2,"of",c)
            for c2 in c.superClasses:
                if c2.identifier not in self.classes:
                    print("    Warning: Undeclared superclass",c2,"of",c)
            for p in c.properties:
                for o in p.objectTypes:
                    if not o.startswith("xsd:") and o!=Prefixes.rdfLangString and o!=Prefixes.rdfsClass and o!=Prefixes.geoPoint and o not in self.classes:
                        print("    Warning: Undeclared range",o,"of property",p,"in class",c)                
                
