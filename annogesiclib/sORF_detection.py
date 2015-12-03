import os
import sys
import copy
from annogesiclib.helper import Helper
from annogesiclib.gff3 import Gff3Parser
from annogesiclib.lib_reader import read_libs, read_wig
from annogesiclib.coverage_detection import replicate_comparison

def get_coverage(sorf, wigs, strand, coverages, medianlist, cutoffs):
    high_cover = -1
    low_cover = -1
    sorf_covers = {}
    for wig_strain, conds in wigs.items():
        if wig_strain == sorf["strain"]:
            for cond, tracks in conds.items():
                sorf_covers[cond] = []
                for track, covers in tracks.items():
                    total_cover = 0
                    first = True
                    if strand == "+":
                        covers = covers[sorf["start"] - 2: sorf["end"] + 1]
                    elif strand == "-":
                        covers = reversed(covers[sorf["start"] - 2: sorf["end"] + 1])
                    for cover in covers:
                        if (cover["strand"] == strand):
                            if (sorf["start"] <= cover["pos"]) and (
                                sorf["end"] >= cover["pos"]):
                                total_cover = total_cover + cover["coverage"]
                                if first:
                                    first = False
                                    high_cover = cover["coverage"]
                                    low_cover = cover["coverage"]
                                else:
                                    if high_cover < cover["coverage"]:
                                        high_cover = cover["coverage"]
                                    if low_cover > cover["coverage"]:
                                        low_cover = cover["coverage"]
                    avg = total_cover / float(sorf["end"] - sorf["start"] + 1)
                    if medianlist is not None:
                        cutoff_cover = get_cutoff(sorf, track,
                                       coverages, medianlist)
                    else:
                        cutoff_cover = coverages
                    if cutoffs is not None:
                        cutoffs[track] = cutoff_cover
                    if avg > float(cutoff_cover):
                        sorf_covers[cond].append({"track": track,
                                                  "high": high_cover,
                                                  "low": low_cover, "avg": avg,
                                                  "type": cover["type"],
                                                  "pos": sorf["start"]})
    return sorf_covers

def import_sorf(inter, sorfs, start, end, type_, fasta, rbs):
    sorfs.append({"strain": inter.seq_id,
                  "strand": inter.strand,
                  "start": start,
                  "end": end,
                  "starts": [str(start)],
                  "ends": [str(end)],
                  "seq": fasta[start-1:end],
                  "type": type_,
                  "print": False,
                  "rbs": rbs})

def detect_rbs_site(fasta, start, fuzzy_rbs, inter, min_rbs, max_rbs):
    detect = []
    pre_miss = 5
    for nts in range(0, start):
        num = 0
        miss = 0
        for nt in fasta[nts:nts + 6]:
            if miss > fuzzy_rbs:
                break
            else:
                if (num == 0) and (nt != "A"):
                    miss += 1
                elif (num == 1) and (nt != "G"):
                    miss += 1
                elif (num == 2) and (nt != "G"):
                    miss += 1
                elif (num == 3) and (nt != "A"):
                    miss += 1
                elif (num == 4) and (nt != "G"):
                    miss += 1
                elif (num == 5) and (nt != "G"):
                    miss += 1
                num += 1
        if miss <= fuzzy_rbs:
            if (miss <= pre_miss):
                if miss < pre_miss:
                    detect = []
                if inter.strand == "+":
                    detect.append(inter.start + nts)
                else:
                    detect.append(inter.start + (len(fasta) - nts) - 1)
                pre_miss = miss
    if len(detect) == 0:
        detect = ["NA"]
    return detect

def check_terminal_seq(seq, start, end, start_codon, stop_codon, source,
                       inter, sorfs, rbs):
    detect = None
    for i in [0, 1, -1]:
        fasta = Helper().extract_gene(seq, start + i, end + i, inter.strand)
        if (fasta[:3] in start_codon) and (fasta[-3:] in stop_codon):
            detect = i
    if detect is not None:
        start = start + detect
        end = end + detect
        import_sorf(inter, sorfs, start, end,
                    source, seq, rbs)

def detect_start_stop(inters, seq, start_codon, stop_codon, max_len, min_len,
                      fuzzy_rbs, min_rbs, max_rbs):
    sorfs = []
    for inter in inters:
        fasta = Helper().extract_gene(seq[inter.seq_id],
                inter.start, inter.end, inter.strand)
        starts = []
        stops = []
        for frame in range(0, 3):
            for index in range(frame, len(fasta), 3):
                if fasta[index:index + 3] in start_codon:
                    starts.append(index)
                elif fasta[index:index + 3] in stop_codon:
                    stops.append(index)
        for start in starts:
            for stop in stops:
                if ((stop - start) > 0) and \
                   (((stop - start) % 3) == 0) and \
                   ((stop - start) <= max_len) and \
                   ((stop - start) >= min_len):
                    rbs = detect_rbs_site(fasta, start, fuzzy_rbs, inter,
                                          min_rbs, max_rbs)
                    if (len(rbs) == 1) and (rbs[0] == "NA"):
                        pass
                    else:
                        if inter.source == "intergenic":
                            if inter.strand == "+":
                                check_terminal_seq(seq[inter.seq_id],
                                                 inter.start + start,
                                                 inter.start + stop + 2,
                                                 start_codon, stop_codon,
                                                 inter.source, inter, sorfs, rbs)
                            else:
                                check_terminal_seq(seq[inter.seq_id],
                                                 inter.start + (len(fasta) - stop - 3),
                                                 inter.start + (len(fasta) - start - 1),
                                                 start_codon, stop_codon,
                                                 inter.source, inter, sorfs, rbs)
                        elif inter.source == "UTR_derived":
                            if inter.strand == "+":
                                check_terminal_seq(seq[inter.seq_id],
                                                 inter.start + start,
                                                 inter.start + stop + 2,
                                                 start_codon, stop_codon,
                                                 inter.attributes["UTR_type"],
                                                 inter, sorfs, rbs)
                            else:
                                check_terminal_seq(seq[inter.seq_id],
                                                 inter.start + (len(fasta) - stop - 3),
                                                 inter.start + (len(fasta) - start - 1),
                                                 start_codon, stop_codon,
                                                 inter.attributes["UTR_type"],
                                                 inter, sorfs, rbs)
    return sorfs

def read_data(inter_gff, tss_file, srna_gff, fasta, utr_detect):
    seq = {}
    inters = []
    tsss = []
    srnas = []
    fh = open(inter_gff)
    for entry in Gff3Parser().entries(fh):
        if ((entry.source == "UTR_derived") and \
           (utr_detect)) or \
           (entry.source == "intergenic"):
            inters.append(entry)
    inters = sorted(inters, key=lambda k: (k.seq_id, k.start))
    fh.close()
    if tss_file is not None:
        fh = open(tss_file)
        for entry in Gff3Parser().entries(fh):
            tsss.append(entry)
        tsss = sorted(tsss, key=lambda k: (k.seq_id, k.start))
        fh.close()
    else:
        tsss = None
    if srna_gff is not None:
        fh = open(srna_gff)
        for entry in Gff3Parser().entries(fh):
            new = {}
            for key, value in entry.attributes.items():
                if "sORF" not in key:
                    new[key] = value
            entry.attributes = copy.deepcopy(new)
            srnas.append(entry)
        srnas = sorted(srnas, key=lambda k: (k.seq_id, k.start))
        fh.close()
    else:
        srnas = None
    with open(fasta, "r") as s_f:
        for line in s_f:
            line = line.strip()
            if line.startswith(">"):
                strain = line[1:]
                seq[strain] = ""
            else:
                seq[strain] = seq[strain] + line
    return inters, tsss, srnas, seq

def check_tss(sorf, tss, utr_fuzzy, checks):
    if ((sorf["start"] - tss.start <= utr_fuzzy) and (
         sorf["start"] - tss.start >= 0) and (sorf["strand"] == "+")) or (
        (tss.start - sorf["end"] <= utr_fuzzy) and (
         tss.start - sorf["end"] >= 0) and (sorf["strand"] == "-")):
        sorf["start_TSS"] = str(tss.start) + tss.strand
        sorf["with_TSS"].append("TSS_" + str(tss.start) + tss.strand)
        checks["start"] = True
        checks["import"] = True
        rbss = []
        if (sorf["rbs"][0] != "NA"):
            if sorf["strand"] == "+":
                for rbs in sorf["rbs"]:
                    if rbs >= tss.start:
                        rbss.append(rbs)
            else:
                for rbs in sorf["rbs"]:
                    if rbs <= tss.start:
                        rbss.append(rbs)
        if len(rbss) != 0:
            checks["rbs"] = rbss

def compare_sorf_tss(sorfs, tsss, tss_file, utr_fuzzy, noafter_tss, no_tss):
    sorfs_all = []
    sorfs_best = []
    if tss_file is not None:
        for sorf in sorfs:
            checks = {"start": False, "rbs": False, "import": False}
            sorf["with_TSS"] = []
            for tss in tsss:
                checks["import"] = False
                if (sorf["strain"] == tss.seq_id) and (
                    sorf["strand"] == tss.strand):
                    if sorf["strand"] == "+":
                        check_tss(sorf, tss, utr_fuzzy, checks)
                    else:
                        check_tss(sorf, tss, utr_fuzzy, checks)
                    if not checks["import"]:
                        if (tss.start <= sorf["start"]) and (
                            tss.start >= sorf["end"]):
                            sorf["with_TSS"].append("TSS_" + str(tss.start) + tss.strand)
            if not checks["start"]:
                sorf["start_TSS"] = "NA"
            if len(sorf["with_TSS"]) == 0:
                sorf["with_TSS"] = ["NA"]
            if (checks["rbs"] and (not noafter_tss) and (not no_tss)):
                sorf["rbs"] = checks["rbs"]
                sorfs_best.append(copy.deepcopy(sorf))
            elif ((sorf["rbs"][0] != "NA") and (noafter_tss) and \
                  (not no_tss) and (checks["start"])):
                sorfs_best.append(copy.deepcopy(sorf))
            elif ((sorf["rbs"][0] != "NA") and (noafter_tss) and \
                  (no_tss)):
                sorfs_best.append(copy.deepcopy(sorf))
            sorfs_all.append(sorf)
    else:
        for sorf in sorfs:
            sorf["with_TSS"] = ["NA"]
            sorf["start_TSS"] = "NA"
            if sorf["rbs"][0] != "NA":
                sorfs_bests.append(copy.deepcopy(sorf))
            sorfs_all.append(sorf)
#    if len(sorfs_all) == 0:
#        sorfs_all = copy.deepcopy(sorfs)
#    if len(sorfs_best) == 0:
#        sorfs_best = copy.deepcopy(sorfs_all)
    return sorfs_all, sorfs_best

def compare_sorf_srna(sorfs, srnas, srna_gff):
    if srna_gff is not None:
        for sorf in sorfs:
            sorf["srna"] = []
            for srna in srnas:
                if (sorf["strain"] == srna.seq_id) and (
                    sorf["strand"] == srna.strand):
                    if ((srna.start <= sorf["start"]) and (
                         srna.end >= sorf["end"])) or (
                        (srna.start >= sorf["start"]) and (
                         srna.end <= sorf["end"])) or (
                        (srna.start <= sorf["start"]) and (
                         srna.end >= sorf["start"]) and (
                         srna.end <= sorf["end"])) or (
                        (srna.start >= sorf["start"]) and (
                         srna.start <= sorf["end"]) and (
                         srna.end >= sorf["end"])):
                        strand = Helper().get_strand_name(srna.strand)
                        sorf["srna"].append(srna.attributes["ID"] + ":" + \
                                     str(srna.start) + "-" + str(srna.end) + \
                                     "_" + strand)
            if len(sorf["srna"]) == 0:
                sorf["srna"] = ["NA"]
    else:
        for sorf in sorfs:
            sorf["srna"] = ["NA"]

def import_overlap(sorf2, final, sorf1, first):
    sorf2["print"] = True
    if final["start"] > sorf2["start"]:
        final["start"] = sorf2["start"]
    if final["end"] < sorf2["end"]:
        final["end"] = sorf2["end"]
    if first:
        final["candidate"] = []
        final["candidate"].append("_".join(["-".join([
                str(sorf1["start"]), str(sorf1["end"])]),
                "TSS:" + sorf1["start_TSS"],
                "RBS:" + str(sorf1["rbs"][0])]))
        first = False
    if "_".join(["-".join([str(sorf2["start"]), str(sorf2["end"])]),
                 "TSS:" + sorf2["start_TSS"],
                 "RBS:" + str(sorf2["rbs"][0])]) not in final["candidate"]:
        final["candidate"].append("_".join(["-".join([
                str(sorf2["start"]), str(sorf2["end"])]),
                "TSS:" + sorf2["start_TSS"],
                "RBS:" + str(sorf2["rbs"][0])]))
    if str(sorf2["start"]) not in final["starts"]:
        final["starts"].append(str(sorf2["start"]))
    if str(sorf2["end"]) not in final["ends"]:
        final["ends"].append(str(sorf2["end"]))
    if sorf2["rbs"] != ["NA"]:
        if (len(final["rbs"]) == 1) and (final["rbs"] == ["NA"]):
            final["rbs"] = sorf2["rbs"]
        else:
            if sorf2["rbs"][0] not in final["rbs"]:
                final["rbs"] = final["rbs"] + sorf2["rbs"]
    return first

def merge(sorfs, seq):
    finals = []
    for sorf1 in sorfs:
        final = copy.deepcopy(sorf1)
        first = True
        import_data = False
        if not sorf1["print"]:
            sorf1["print"] = True
            for sorf2 in sorfs:
                overlap = False
                if (final["strain"] == sorf2["strain"]) and (
                    final["strand"] == sorf2["strand"]) and (
                    final["rbs"] == sorf2["rbs"]):
                    if (final["start"] >= sorf2["start"]) and (
                        final["end"] <= sorf2["end"]):
                        overlap = True
                    elif (final["start"] >= sorf2["start"]) and (
                          final["start"] <= sorf2["end"]) and (
                          final["end"] >= sorf2["end"]):
                        overlap = True
                    elif (final["start"] <= sorf2["start"]) and (
                          final["end"] >= sorf2["start"]) and (
                          final["end"] <= sorf2["end"]):
                        overlap = True
                    elif (final["start"] <= sorf2["start"]) and (
                          final["end"] >= sorf2["end"]):
                        overlap = True
                    elif (sorf2["start"] > final["end"]):
                        break
                    if overlap:
                        import_data = True
                        first = import_overlap(sorf2, final, sorf1, first)
            final["seq"] = Helper().extract_gene(seq[final["strain"]],
                           final["start"], final["end"], final["strand"])
            new = {}
            for key, value in final.items():
                if "print" not in key:
                    new[key] = value
            final = copy.deepcopy(new)
            finals.append(final)
    return finals

def assign_utr_cutoff(coverages, utr_type, medians):
    if coverages[utr_type] == "median":
        cutoff = medians["median"]
    elif coverages[utr_type] == "mean":
        cutoff = medians["mean"]
    else:
        cutoff = float(coverages[utr_type])
    return cutoff

def get_cutoff(sorf, track, coverages, medians):
    if sorf["type"] == "intergenic":
        cutoff_cover = float(coverages["inter"])
    elif ("5utr" in sorf["type"]) and ("3utr" in sorf["type"]):
        cutoff_utr3 = assign_utr_cutoff(coverages, "3utr",
                          medians[sorf["strain"]]["3utr"][track])
        cutoff_utr5 = assign_utr_cutoff(coverages, "5utr",
                          medians[sorf["strain"]]["5utr"][track])
        cutoff_cover = min(cutoff_utr5, cutoff_utr3)
    elif ("5utr" in sorf["type"]):
        cutoff_cover = assign_utr_cutoff(coverages, "5utr",
                          medians[sorf["strain"]]["5utr"][track])
    elif ("3utr" in sorf["type"]):
        cutoff_cover = assign_utr_cutoff(coverages, "3utr",
                          medians[sorf["strain"]]["3utr"][track])
    elif ("interCDS" in sorf["type"]):
        cutoff_cover = assign_utr_cutoff(coverages, "interCDS",
                          medians[sorf["strain"]]["interCDS"][track])
    return cutoff_cover

def get_attribute(num, name, start_tss, sorf, type_):
    if type_ == "intergenic":
        attribute_string = ";".join(
            ["=".join(items) for items in (["ID", "sorf" + str(num)],
                             ["Name", "sORF_" + name],
                             ["start_TSS", start_tss],
                             ["with_TSS", "&".join(sorf["with_TSS"])],
                             ["sRNA", "&".join(sorf["srna"])],
                             ["RBS", "&".join(sorf["rbs"])],
                             ["frame_shift", str(sorf["shift"])])])
    else:
        attribute_string = ";".join(
            ["=".join(items) for items in (["ID", "sorf" + str(num)],
                             ["Name", "sORF_" + name],
                             ["start_TSS", start_tss],
                             ["with_TSS", "&".join(sorf["with_TSS"])],
                             ["UTR_type", sorf["type"]],
                             ["sRNA", "&".join(sorf["srna"])],
                             ["RBS", "&".join(sorf["rbs"])],
                             ["frame_shift", str(sorf["shift"])])])
    return attribute_string

def check_start_and_tss_point(sorf):
#    if sorf["start_TSS"] != "NA":
#        if (sorf["strand"] == "+"):
#            start_TSS = sorf["start_TSS"].replace("TSS_", "")
#            start_TSS = start_TSS.replace("+", "")
#            if (sorf["start"] > int(start_TSS)):
#                sorf["start"] = int(start_TSS)
#        elif (sorf["strand"] == "-"):
#            start_TSS = sorf["start_TSS"].replace("TSS_", "")
#            start_TSS = start_TSS.replace("-", "")
#            if (sorf["end"] < int(start_TSS)):
#                sorf["end"] = int(start_TSS)
    tsss = []
    for tss in sorf["with_TSS"]:
        if tss != "NA":
            if (int(tss.replace("TSS_", "")[:-1]) >= int(sorf["start"])) and (
                int(tss.replace("TSS_", "")[:-1]) <= int(sorf["end"])):
                tsss.append(tss)
        else:
            tsss.append(tss)
    sorf["with_TSS"] = copy.deepcopy(tsss)

def compare_rbs_start(sorf, min_rbs, max_rbs):
    detect = False
    if (len(sorf["rbs"]) == 1) and (sorf["rbs"][0] == "NA"):
        pass
    else:
        new_rbss = []
        for rbs in sorf["rbs"]:
            if rbs != "NA":
                if sorf["strand"] == "+":
                    for start in sorf["starts"]:
                        if ((int(start) - int(rbs)) >= min_rbs + 6) and (
                            (int(start) - int(rbs)) <= max_rbs + 6) and (
                            rbs not in new_rbss):
                            new_rbss.append(rbs)
                            detect = True
                else:
                    for end in sorf["ends"]:
                        if ((int(rbs) - int(end)) >= min_rbs + 6) and (
                            (int(rbs) - int(end)) <= max_rbs + 6) and (
                            rbs not in new_rbss):
                            new_rbss.append(rbs)
                            detect = True
        if not detect:
            sorf["rbs"] = ["NA"]
        else:
            sorf["rbs"] = new_rbss
    return detect

def gen_new_candidates(sorf, min_rbs, max_rbs):
    new_candidates = []
    for start in sorf["starts"]:
        for end in sorf["ends"]:
            if ((int(end) - int(start) + 1) % 3) == 0:
                for rbs in sorf["rbs"]:
                    if (sorf["strand"] == "+") and (
                        (int(start) - rbs) >= (min_rbs + 6)) and (
                        (int(start) - rbs) <= (max_rbs + 6)):
                        for tss in sorf["with_TSS"]:
                            if int(tss.split("_")[-1][:-1]) > int(start):
                                break
                            pre_tss = tss
                        new_candidates.append("_".join(["-".join([
                                  start, end]), pre_tss.replace("_", ":"),
                                  "RBS:" + str(rbs)]))
                    elif (sorf["strand"] == "-") and (
                        (rbs - int(end)) >= (min_rbs + 6)) and (
                        (rbs - int(end)) <= (max_rbs + 6)):
                        for tss in sorf["with_TSS"]:
                            if int(tss.split("_")[-1][:-1]) <= int(start):
                                break
                        new_candidates.append("_".join(["-".join([
                                  start, end]), tss.replace("_", ":"),
                                  "RBS:" + str(rbs)]))
    return new_candidates

def check_candidates_srnas(sorf, min_rbs, max_rbs):
    new_candidates = []
    for cand in sorf["candidate"]:
        infos = cand.split("_")
        start = infos[0].split("-")[0]
        end = infos[0].split("-")[1]
        rbs = int(infos[-1].split(":")[-1])
        if (start in sorf["starts"]) and (
            end in sorf["ends"]) and (
            rbs in sorf["rbs"]):
            new_candidates.append(cand)
    if len(new_candidates) == 0:
        new_candidates = gen_new_candidates(sorf, min_rbs, max_rbs)
    new_srnas = []
    if (len(sorf["srna"]) == 1) and (sorf["srna"][0] == "NA"):
        pass
    else:
        for srna in sorf["srna"]:
            srna_strand = srna.split("_")[-1]
            if srna_strand == "r":
                strand = "-"
            else:
                strand = "+"
            srna_end = int(srna.split("_")[0].split("-")[-1])
            srna_start = int(srna.split("_")[0].split("-")[0].split(":")[-1])
            if (strand == sorf["strand"]):
                if ((srna_start <= int(sorf["start"])) and (
                     srna_end >= int(sorf["end"]))) or (
                    (srna_start >= int(sorf["start"])) and (
                     srna_end <= int(sorf["end"]))) or (
                    (srna_start <= int(sorf["start"])) and (
                     srna_end >= int(sorf["start"])) and (
                     srna_end <= int(sorf["end"]))) or (
                    (srna_start >= int(sorf["start"])) and (
                     srna_start <= int(sorf["end"])) and (
                     srna_end >= int(sorf["end"]))):
                    new_srnas.append(srna)
    sorf["candidate"] = new_candidates
    if len(new_srnas) != 0:
        sorf["srna"] = new_srnas
    else:
        sorf["srna"] = ["NA"]

def check_start_end(sorf, min_rbs, max_rbs, min_len, max_len, fasta):
    if (len(sorf["rbs"]) == 1) and (sorf["rbs"][0] == "NA"):
        pass
    else:
        if sorf["strand"] == "+":
            starts = []
            for start in sorf["starts"]:
                if int(start) < min(sorf["rbs"]):
                    continue
                else:
                    for rbs in sorf["rbs"]:
                        if ((int(start) - int(rbs)) >= min_rbs + 6) and (
                            (int(start) - int(rbs)) <= max_rbs + 6) and (
                            start not in starts):
                            starts.append(start)
            ends = []
            for end in sorf["ends"]:
                for start in starts:
                    if ((int(end) - int(start) + 1) % 3 == 0) and (
                        (int(end) - int(start) + 1) >= min_len) and (
                        (int(end) - int(start) + 1) <= max_len) and (
                        end not in ends):
                        if end not in ends:
                            ends.append(end)
        else:
            ends = []
            for end in sorf["ends"]:
                if int(end) > max(sorf["rbs"]):
                    continue
                else:
                    for rbs in sorf["rbs"]:
                        if ((int(rbs) - int(end)) >= min_rbs + 6) and (
                            (int(rbs) - int(end)) <= max_rbs + 6) and (
                            end not in ends):
                            ends.append(end)
            starts = []
            for start in sorf["starts"]:
                for end in ends:
                    if ((int(end) - int(start) + 1) % 3 == 0) and (
                        (int(end) - int(start) + 1) >= min_len) and (
                        (int(end) - int(start) + 1) <= max_len) and (
                        start not in starts):
                        if start not in starts:
                            starts.append(start)
        sorf["starts"] = starts
        sorf["ends"] = ends
        sorf["start"] = min(map(int, starts))
        sorf["end"] = max(map(int, ends))
        sorf["seq"] = Helper().extract_gene(fasta[sorf["strain"]],
                      sorf["start"], sorf["end"], sorf["strand"])
        check_candidates_srnas(sorf, min_rbs, max_rbs)

def detect_frame_shift(sorf):
    stand = sorf["starts"][0]
    shift = {"0": False, "1": False, "2": False}
    sorf["shift"] = 0
    for start in sorf["starts"]:
        if ((int(start) - int(stand)) % 3) == 0:
            shift["0"] = True
        elif ((int(start) - int(stand)) % 3) == 1:
            shift["1"] = True
        elif ((int(start) - int(stand)) % 3) == 2:
            shift["2"] = True
    for key, value in shift.items():
        if value:
            sorf["shift"] += 1

def print_file(sorf, sorf_datas, num, out_g, out_t, table_best, print_all,
               min_rbs, max_rbs, file_type, min_len, max_len):
    name = '%0*d' % (5, num)
    if sorf["type"] == "intergenic":
        source = "intergenic"
        type_ = "Intergenic"
        for index in range(len(sorf["rbs"])):
            if (sorf["rbs"][index] == "NA") and (len(sorf["rbs"]) == 1):
                pass
            else:
                sorf["rbs"][index] = "RBS_" + str(sorf["rbs"][index])
        attribute_string = get_attribute(num, name, sorf["start_TSS"], sorf, "intergenic")
    else:
        source = "UTR_derived"
        if ("3utr" in sorf["type"]) and ("5utr" in sorf["type"]):
            type_ = "3'UTR_derived;5'UTR_derived"
        elif ("3utr" in sorf["type"]):
            type_ = "3'UTR_derived"
        elif ("5utr" in sorf["type"]):
            type_ = "5'UTR_derived"
        elif ("interCDS" in sorf["type"]):
            type_ = "interCDS"
        for index in range(len(sorf["rbs"])):
            if (sorf["rbs"][index] == "NA") and (len(sorf["rbs"]) == 1):
                pass
            else:
                sorf["rbs"][index] = "RBS_" + str(sorf["rbs"][index])
        attribute_string = get_attribute(num, name, sorf["start_TSS"], sorf, "utr")
    info = "\t".join([str(field) for field in [
                      sorf["strain"], source, "sORF", str(sorf["start"]),
                      str(sorf["end"]), ".", sorf["strand"],
                      ".", attribute_string]])
    out_g.write(info + "\n")
    check_frag = False
    check_tex = False
    if ("frag" in ";".join(sorf_datas["conds"].keys())) and (
        "tex" in ";".join(sorf_datas["conds"].keys())):
        lib_type = "TEX+/-;Fragmented"
    elif ("frag" in ";".join(sorf_datas["conds"].keys())):
        lib_type = "Fragmented"
    elif ("tex" in ";".join(sorf_datas["conds"].keys())):
        lib_type = "TEX+/-"
    print_table(out_t, sorf, name, type_, lib_type,
                sorf_datas, table_best, print_all)

def print_table(out_t, sorf, name, type_, lib_type,
                sorf_datas, table_best, print_all):
    out_t.write("\t".join([sorf["strain"], "sORF_" + name, str(sorf["start"]),
                           str(sorf["end"]), sorf["strand"], type_,
                           ";".join(sorf["with_TSS"]), ";".join(sorf["rbs"]),
                           ";".join(sorf["starts"]), ";".join(sorf["ends"]),
                           ";".join(sorf["srna"]), str(sorf["shift"]),
                           lib_type, str(sorf_datas["best"]),
                           str(sorf_datas["high"]), str(sorf_datas["low"]),
                           ";".join(sorf["srna"]), str(sorf_datas["best"]),
                           str(sorf_datas["high"]),
                           str(sorf_datas["low"])]) + "\t")
    if not table_best:
        first = True
        for data in sorf_datas["detail"]:
            if first:
                out_t.write("{0}(avg={1};high={2};low={3})".format(
                            data["track"], data["avg"],
                            data["high"], data["low"]))
                first = False
            else:
                out_t.write(";{0}(avg={1};high={2};low={3})".format(
                            data["track"], data["avg"],
                            data["high"], data["low"]))
    else:
        out_t.write("{0}(avg={1};high={2};low={3})".format(
                    sorf_datas["track"], sorf_datas["best"],
                    sorf_datas["high"], sorf_datas["low"]))
    out_t.write("\t" + sorf["seq"])
    if print_all:
        out_t.write("\t" + ";".join(sorf["candidate"]))
    out_t.write("\n")

def get_inter_coverage(inters, inter_covers):
    for datas in inters:
        for cond, covers in datas.items():
            for inter in covers:
                if inter["track"] not in inter_covers.keys():
                    inter_covers[inter["track"]] = []
                inter_covers[inter["track"]].append(inter["avg"])

def detect_utr_type(inter, utr_type, med_inters, wigs, strand, background):
    if inter.attributes["UTR_type"] == utr_type:
        inter_datas = {}
        inter_datas["strain"] = inter.seq_id
        inter_datas["strand"] = inter.strand
        inter_datas["start"] = inter.start
        inter_datas["end"] = inter.end
        inter_datas = get_coverage(inter_datas, wigs, strand, background, None, None)
        med_inters[inter.seq_id][utr_type].append(inter_datas)

def median_score(lst, cutoff):
    if "p_" in cutoff:
        per = float(cutoff.split("_")[-1])
        sortedLst = sorted(lst)
        lstLen = len(lst)
        index = int((lstLen - 1) * per)
        if lstLen != 0:
            return sortedLst[index]
        else:
            return 0
    else:
        return cutoff

def mean_score(lst):
    total = 0
    for li in lst:
        total = total + li
    if len(lst) != 0:
        return (total / len(lst))
    else:
        return 0

def validate_tss(starts, ends, sorf, utr_fuzzy):
    tsss = []
    start_pos = "NA"
    if sorf["with_TSS"][0] != "NA":
        for tss in sorf["with_TSS"]:
            tss_start = int(tss.replace("TSS_", "")[:-1])
            if sorf["strand"] == "+":
                if (tss_start >= min(starts) - utr_fuzzy) and (
                    tss_start <= max(ends)):
                    tsss.append(tss)
                    if (tss_start >= min(starts) - utr_fuzzy) and (
                        tss_start <= min(starts)):
                        start_pos = tss
            else:
                if (tss_start >= min(starts)) and (
                    tss_start <= max(ends) + utr_fuzzy):
                    tsss.append(tss)
                    if (tss_start <= min(ends) + utr_fuzzy) and (
                        tss_start >= min(ends)):
                        start_pos = tss
                        break
    else:
        tsss = ["NA"]
    return (tsss, start_pos)

def validate_srna(starts, ends, sorf):
    srnas = []
    for srna in sorf["srna"]:
        if srna == "NA":
            break
        else:
            datas = srna.split(":")[1][:-2].split("-")
            start = int(datas[0])
            end = int(datas[1])
            for index in range(0, len(starts)):
                if ((start <= starts[index]) and (
                     end >= ends[index])) or (
                    (start >= starts[index]) and (
                     end <= ends[index])) or (
                    (start >= starts[index]) and (
                     start <= ends[index]) and (
                     end >= ends[index])) or (
                    (start <= starts[index]) and (
                     end >= starts[index]) and (
                     end <= ends[index])):
                    srnas.append(srna)
                    break
    if len(srnas) == 0:
        srnas = ["NA"]
    return srnas

def get_best(sorfs, utr_fuzzy, tss_file, srna_file, no_srna, no_tss):
    final_sorfs = []
    for sorf in sorfs:
        if (tss_file is not None):
            if (sorf["with_TSS"][0] != "NA") or (no_tss):
                cands = []
                starts = []
                ends = []
                tmp_sorf = copy.deepcopy(sorf)
                for candidate in sorf["candidate"]:
                    tss = candidate.split("_TSS:")[1].split("_RBS:")[0]
                    rbs = candidate.split("_TSS:")[1].split("_RBS:")[-1]
                    if (tss != "NA") or (no_tss):
                        datas = candidate.split("_TSS:")[0].split("-")
                        cands.append("-".join([
                              str(datas[0]), str(datas[1])]) + "_TSS:" + tss + "_RBS:" + rbs)
                        starts.append(int(datas[0]))
                        ends.append(int(datas[1]))
                tmp_sorf["start"] = min(starts)
                tmp_sorf["end"] = max(ends)
                tmp_sorf["starts"] = sorf["starts"]
                tmp_sorf["ends"] = sorf["ends"]
                tmp_sorf["candidate"] = cands
                tsss_datas = validate_tss(starts, ends, sorf, utr_fuzzy)
                tmp_sorf["with_TSS"] = tsss_datas[0]
                tmp_sorf["start_TSS"] = tsss_datas[1]
                if srna_file is not None:
                    tmp_sorf["sRNA"] = validate_srna(starts, ends, sorf)
                    if (no_srna) and (tmp_sorf["sRNA"][0] == "NA"):
                        final_sorfs.append(tmp_sorf)
                    elif not no_srna:
                        final_sorfs.append(tmp_sorf)
        elif srna_file is not None:
            if (no_srna) and (tmp_sorf["sRNA"][0] == "NA"):
                final_sorfs.append(sorf)
            elif not no_srna:
                    final_sorfs.append(tmp_sorf)
    if len(final_sorfs) == 0:
        final_sorfs = sorfs
    return final_sorfs

def coverage_and_output(sorfs, mediandict, wigs_f, wigs_r, texs, out_g, out_t,
                        tex_notex, replicates, coverages, table_best, print_all,
                        min_rbs, max_rbs, file_type, min_len, max_len, fasta):
    out_g.write("##gff-version 3\n")
    if print_all:
        out_t.write("\t".join(["strain", "Name", "start", "end", "strand", "type",
                    "TSS", "RBS", "all_start_points", "all_stop_pointss",
                    "sRNA_confliction", "frame_shift", "lib_type", "best_avg_coverage",
                    "best_highest_coverage", "best_lowest_coverage",
                    "track_detail", "seq", "combinations"]) + "\n")
    else:
        out_t.write("\t".join(["strain", "Name", "start", "end", "strand", "type",
                    "TSS", "RBS", "all_start_points", "all_stop_points",
                    "sRNA_confliction", "frame_shift", "lib_type", "best_avg_coverage",
                    "best_highest_coverage", "best_lowest_coverage",
                    "track_detail", "seq"]) + "\n")
    num = 0
    for sorf in sorfs:
        if (compare_rbs_start(sorf, min_rbs, max_rbs) and file_type == "best") or (
            file_type == "all"):
            if file_type == "best":
                check_start_end(sorf, min_rbs, max_rbs, min_len, max_len, fasta)
            detect_frame_shift(sorf)
            cutoffs = {}
            if sorf["strand"] == "+":
                sorf_covers = get_coverage(sorf, wigs_f, "+", coverages,
                                           mediandict, cutoffs)
            else:
                sorf_covers = get_coverage(sorf, wigs_r, "-", coverages,
                                           mediandict, cutoffs)
            if len(sorf_covers) != 0:
                sorf_info = replicate_comparison(sorf_covers, texs,
                                    sorf["strand"], None, tex_notex, replicates,
                                    "sORF", None, cutoffs, None, texs, cutoffs)
                if len(sorf_info["conds"].keys()) != 0:
                    print_file(sorf, sorf_info, num, out_g, out_t, table_best,
                               print_all, min_rbs, max_rbs, file_type,
                               min_len, max_len)
                    num += 1

def detect_inter_type(inters, wigs_f, wigs_r, background):
    med_inters = {}
    strain = ""
    for inter in inters:
        if inter.seq_id != strain:
            strain = inter.seq_id
            med_inters[inter.seq_id] = {"5utr": [], "3utr": [], "interCDS": []}
        if (inter.source == "UTR_derived") and (inter.strand == "+"):
            detect_utr_type(inter, "5utr", med_inters, wigs_f, "+", background)
            detect_utr_type(inter, "3utr", med_inters, wigs_f, "+", background)
            detect_utr_type(inter, "interCDS", med_inters,
                            wigs_f, "+", background)
        elif (inter.source == "UTR_derived") and (inter.strand == "-"):
            detect_utr_type(inter, "5utr", med_inters, wigs_r, "-", background)
            detect_utr_type(inter, "3utr", med_inters, wigs_r, "-", background)
            detect_utr_type(inter, "interCDS", med_inters,
                            wigs_r, "-", background)
    return med_inters

def set_median(covers, mediandict, coverages):
    for strain, utrs in covers.items():
        mediandict[strain] = {"3utr": {}, "5utr": {}, "interCDS": {}}
        for utr, tracks in utrs.items():
            for track, avgs in tracks.items():
                if track not in mediandict[strain][utr].keys():
                    mediandict[strain][utr][track] = {}
                mediandict[strain][utr][track] = {"median": median_score(avgs,
                                                            coverages[utr])}
    for utr, value in coverages.items():
        if type(value) is str:
            if "p_" in value:
                coverages[utr] = "median"

def compute_candidate_best(sorfs_best):
    for sorf in sorfs_best:
        sorf["candidate"] = []
        sorf["candidate"].append("_".join(["-".join([
                          str(sorf["start"]), str(sorf["end"])]),
                          "TSS:" + sorf["start_TSS"],
                          "RBS:" + str(sorf["rbs"][0])]))

def set_coverage(utr3_coverage, utr5_coverage, inter_coverage, interCDS_coverage):
    if "n_" in utr3_coverage:
        utr3_coverage = float(utr3_coverage.split("_")[-1])
    if "n_" in utr5_coverage:
        utr5_coverage = float(utr5_coverage.split("_")[-1])
    if "n_" in interCDS_coverage:
        interCDS_coverage = float(interCDS_coverage.split("_")[-1])
    coverages = {"3utr": utr3_coverage, "5utr": utr5_coverage,
                 "inter": inter_coverage, "interCDS": interCDS_coverage}
    return coverages

def sorf_detection(fasta, srna_gff, inter_gff, tss_file, utr_fuzzy, utr_detect,
                   input_libs, tex_notex, replicates, inter_coverage,
                   utr3_coverage, utr5_coverage, interCDS_coverage, wig_f_file,
                   wig_r_file, wig_folder, start_codon, stop_codon, table_best,
                   max_len, min_len, out_prefix, background, fuzzy_rbs, print_all,
                   no_srna, noafter_tss, no_tss, min_rbs, max_rbs):
    coverages = set_coverage(utr3_coverage, utr5_coverage,
                             inter_coverage, interCDS_coverage)
    libs, texs = read_libs(input_libs, wig_folder)
    inters, tsss, srnas, seq = read_data(inter_gff, tss_file, srna_gff,
                                         fasta, utr_detect)
    wigs_f = read_wig(wig_f_file, "+", libs)
    wigs_r = read_wig(wig_r_file, "-", libs)
    med_inters = detect_inter_type(inters, wigs_f, wigs_r, background)
    inter_covers = {}
    mediandict = {}
    for strain, meds in med_inters.items():
        inter_covers[strain] = {"5utr": {}, "3utr": {}, "interCDS": {}}
        for type_, covers in meds.items():
            get_inter_coverage(covers, inter_covers[strain][type_])
    set_median(inter_covers, mediandict, coverages)
    out_ag = open("_".join([out_prefix, "all.gff"]), "w")
    out_at = open("_".join([out_prefix, "all.csv"]), "w")
    out_bg = open("_".join([out_prefix, "best.gff"]), "w")
    out_bt = open("_".join([out_prefix, "best.csv"]), "w")
    sorfs = detect_start_stop(inters, seq, start_codon, stop_codon, max_len,
                              min_len, fuzzy_rbs, min_rbs, max_rbs)
    sorfs_all, sorfs_best = compare_sorf_tss(sorfs, tsss, tss_file,
                                    utr_fuzzy, noafter_tss, no_tss)
    compare_sorf_srna(sorfs_all, srnas, srna_gff)
    compare_sorf_srna(sorfs_best, srnas, srna_gff)
    sorfs_all = sorted(sorfs_all, key=lambda k: (k["strain"], k["start"]))
    sorfs_best = sorted(sorfs_best, key=lambda k: (k["strain"], k["start"]))
    sorfs_all = merge(sorfs_all, seq)
    sorfs_best = merge(sorfs_best, seq)
    final_best = get_best(sorfs_best, utr_fuzzy, tss_file,
                          srna_gff, no_srna, no_tss)
    coverage_and_output(sorfs_all, mediandict, wigs_f, wigs_r, texs, out_ag, out_at,
                        tex_notex, replicates, coverages, table_best, print_all,
                        min_rbs, max_rbs, "all", min_len, max_len, seq)
    coverage_and_output(final_best, mediandict, wigs_f, wigs_r, texs, out_bg,
                        out_bt, tex_notex, replicates, coverages, table_best,
                        print_all, min_rbs, max_rbs, "best", min_len, max_len, seq)
    out_ag.close()
    out_at.close()
    out_bg.close()
    out_bt.close()
