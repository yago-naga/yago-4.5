import sys
from wasabi import msg, table
import csv

msg.info("Initiated...")
gold_standard = ""
output_file = ""
not_in_output = []
not_in_gold = []

try:
    gold_standard = sys.argv[1]
    output_file = sys.argv[2]
    msg.text(f"gold standard: {str(gold_standard)}")
    msg.text(f"output file: {str(output_file)}")
except:
    msg.fail("Problem with arguments provided. Please provide the path to the gold standard file and the output file to test.")
    quit()

with msg.loading("Analyzing the files..."):
    err_file = "gold standard"
    try:
        with open(gold_standard) as file:
            tsv_file = csv.reader(file, delimiter="\t")
            for golden_line in tsv_file:
                found = False
                err_file = "output"
                if golden_line != []:
                    with open(output_file) as file2:
                        tsv_file2 = csv.reader(file, delimiter="\t")
                        for output_line in tsv_file2:
                            if golden_line == output_line:
                                found = True
                                break
                        file2.close()
                    if not found:
                        not_in_output.append(golden_line)
        file.close()

        with open(output_file) as file:
            tsv_file = csv.reader(file, delimiter="\t")
            for output_line in tsv_file:
                found = False
                err_file = "output"
                if output_line != []:
                    with open(gold_standard) as file2:
                        tsv_file2 = csv.reader(file, delimiter="\t")
                        for golden_line in tsv_file2:
                            if output_line == golden_line:
                                found = True
                                break
                        file2.close()
                    if not found:
                        not_in_gold.append(output_line)
        file.close()                
    except FileNotFoundError:
        msg.fail(f"Invalid file path for {err_file} file.")
        try:
            exit()
        except:
            print("Execution finished")

msg.good("Files analyzed successfully!")
msg.text(f"Number of files in golden standard and not in output file: {len(not_in_output)}")
msg.text("Lines:", color="#FFD700")
for line in not_in_output:
    msg.text(f"\t\t{str(line)}")
msg.text(f"Number of files in output file and not in golden standard: {len(not_in_output)}")
msg.text("Lines:", color="#FFD700")
for line in not_in_gold:
    msg.text(f"\t\t{str(line)}")

