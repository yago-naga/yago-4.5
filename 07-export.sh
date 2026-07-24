# Exports YAGO into a ZIP file and to the Web server
# CC-BY 2023-2026 Fabian M. Suchanek
# run with nohup

cd yago-data

######################## Tiny YAGO #############################

echo "Creating tiny YAGO..."
date +"  Current time: %F %T"
# Add schema
cp 01-yago-final-schema.ttl yago-tiny.ttl
# Add taxonomy
grep -v -P '@prefix' 05-yago-final-taxonomy.tsv >> yago-tiny.ttl
# Add facts
grep -P 'yago:A[^\t]+\t(rdf:type\t|[^\t]+\t("|yago:A))' 05-yago-final-wikipedia.tsv | grep -v -P "_Q[0-9]+" >> yago-tiny.ttl
# Add units and their types and labels
grep -oP '"\^\^\K[a-zA-Z0-9_:]+' yago-tiny.ttl | sort | uniq > yago-units.txt
sed 's/^/^/; s/$/\t(rdf:type|rdfs:label)/' yago-units.txt > yago-units-patterns.txt
grep -E -f yago-units-patterns.txt 05-yago-final-wikipedia.tsv >> yago-tiny.ttl
rm yago-units.txt
rm yago-units-patterns.txt
# Add labels of classes after the last schema-declared one
grep -m 1 -A 1000000 'schema:MedicalCondition' 05-yago-final-taxonomy.tsv |sed '1d' | cut -f1 | grep -v -P "yago:A" | sort | uniq | sed 's/.*/&\trdfs:label\t"&"@en\t./' >> yago-tiny.ttl
# Zip the file
rm yago-tiny.zip
zip yago-tiny.zip yago-tiny.ttl
echo "done"

if false; then

######################## YAGO Entity List #############################

# This entity list is used for the LELA disambiguation system

echo "Generating YAGO entity list..."
  sed -n 's/^yago:\([^\t]\+\)\trdfs:comment\t"\([^"]\+\)"@en.*/{"id": "yago:\1", "title": "\1", "description": "\2"}/p' 05-yago-final-wikipedia.tsv > yago-entities.jsonl
  zip -m yago-entities.jsonl.zip yago-entities.jsonl
echo "done"

######################## Export to Qlever #############################

# Data files (renamed from .tsv to .ttl for QLever indexing)
scp 01-yago-final-schema.ttl yago@yago.r2.enst.fr:/data/qlever/yago-schema.ttl
scp 05-yago-final-taxonomy.tsv yago@yago.r2.enst.fr:/data/qlever/yago-taxonomy.ttl
scp 05-yago-final-wikipedia.tsv yago@yago.r2.enst.fr:/data/qlever/yago-wikipedia.ttl
scp 05-yago-final-wikipedia-labels.tsv yago@yago.r2.enst.fr:/data/qlever/yago-wikipedia-labels.ttl
scp 05-yago-final-beyond-wikipedia.tsv yago@yago.r2.enst.fr:/data/qlever/yago-beyond-wikipedia.ttl
scp 05-yago-final-beyond-wikipedia-labels.tsv yago@yago.r2.enst.fr:/data/qlever/yago-beyond-wikipedia-labels.ttl

# Meta file - NOT renamed to .ttl (uses RDF-star syntax that QLever cannot parse)
scp 05-yago-final-meta.tsv yago@yago.r2.enst.fr:/data/qlever/yago-meta.tsv

# Log and mapping files (for excluded facts database)
scp 02-make-taxonomy.log yago@yago.r2.enst.fr:/data/qlever/
scp 03-make-facts.log yago@yago.r2.enst.fr:/data/qlever/
scp 04-make-type-check.log yago@yago.r2.enst.fr:/data/qlever/
scp 04-yago-ids.tsv yago@yago.r2.enst.fr:/data/qlever/


######################## Export to Web server #############################

declare -A yagoFiles=( 
    ["schema"]="01-yago-final-schema.ttl"
	["taxonomy"]="05-yago-final-taxonomy.tsv"
    ["facts"]="05-yago-final-wikipedia.tsv"
	["labels"]="05-yago-final-wikipedia-labels.tsv" 
    ["beyond-wikipedia"]="05-yago-final-beyond-wikipedia.tsv" 
	["beyond-wikipedia-labels"]="05-yago-final-beyond-wikipedia-labels.tsv" 
    ["meta"]="05-yago-final-meta.tsv"
)
version="4.6"

echo "Packing YAGO files..."
rm yago.zip
for file in "${!yagoFiles[@]}"
do
    echo "  Packing $file..."
    mv "${yagoFiles[$file]}" yago-$file.ttl
    zip yago-$file.zip yago-$file.ttl
    zip yago.zip yago-$file.ttl
    mv yago-$file.ttl "${yagoFiles[$file]}"
    echo "  done"
done
echo "done"
  
echo "Copying individual YAGO files to Web server..."
for file in "${!yagoFiles[@]}"
do
    echo "  Copying $file..."
    scp yago-$file.zip yago@yago.r2.enst.fr:/data/public/yago4.5/yago-$version-$file.zip
    echo "  done"
done
echo "done"

echo "Copying collective YAGO files to Web server..."
scp yago.zip yago@yago.r2.enst.fr:/data/public/yago4.5/yago-$version.zip
scp yago-tiny.zip yago@yago.r2.enst.fr:/data/public/yago4.5/yago-$version-tiny.zip
scp 06-upper-taxonomy.html yago@yago.r2.enst.fr:~/website/content/schema.php
scp yago-entities.jsonl.zip yago@yago.r2.enst.fr:/data/public/yago4.5/yago-entities.jsonl.zip
echo "done"
date +"Current time: %F %T"

fi