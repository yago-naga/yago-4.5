# Exports YAGO into a ZIP file and to the Web server
# CC-BY 2023-2025 Fabian M. Suchanek

cd yago-data

echo "Creating tiny YAGO..."
date +"  Current time: %F %T"
cp 01-yago-final-schema.ttl yago-tiny.ttl
grep -v -P '@prefix' 05-yago-final-taxonomy.tsv >> yago-tiny.ttl
grep -P 'yago:A[^\t]+\t[^\t]+\t("|yago:A|schema:)' 05-yago-final-wikipedia.tsv >> yago-tiny.ttl
rm yago-tiny.zip
zip yago-tiny.zip yago-tiny.ttl
echo "done"

declare -A yagoFiles=( 
    ["schema"]="01-yago-final-schema.ttl"
	["taxonomy"]="05-yago-final-taxonomy.tsv"
    ["facts"]="05-yago-final-wikipedia.tsv"
	["labels"]="05-yago-final-wikipedia-labels.tsv" 
    ["beyond-wikipedia"]="05-yago-final-beyond-wikipedia.tsv" 
	["beyond-wikipedia-labels"]="05-yago-final-beyond-wikipedia-labels.tsv" 
    ["meta"]="05-yago-final-meta.tsv"
)
version="4.5.1.0"

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

echo "Generating YAGO entity list..."
  sed -n 's/^yago:\([^\t]\+\)\trdfs:comment\t"\([^"]\+\)"@en/{"id": "yago:\1", "title": "\1", "description": "\2", "clean_id": "\1"}/p' 05-yago-final-wikipedia.tsv > yago-entities.jsonl
  rm 
  zip -m yago-entities.jsonl.zip yago-entities.jsonl
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
