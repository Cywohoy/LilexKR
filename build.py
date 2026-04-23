#!/bin/env python3

import os
import copy
from fontTools.ttLib import TTFont
from fontTools.merge import Merger
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib.tables._g_l_y_f import Glyph
import fontTools.ttLib.tables.otTables as ot

FONT_VERSION="1.000"

NEW_FAMILY_NAME_STD = "LilexKR Std"             # 영문 600 : 한글 1200 (1:2) 
NEW_FAMILY_NAME_COMPACT = "LilexKR Compact"     # 영문 528 : 한글 1056 (1:2) --- Monoplex KR과 동일한 너비임
NEW_FAMILY_NAME_WIDE = "LilexKR 35"             # 영문 600 : 한글 1000 (3:5)
LATIN_DIR = "source/Lilex"
KR_DIR = "source/IBM_Plex_Sans_KR"
OUTPUT_DIR = "output"

WEIGHT_MAP = {
    "Thin": "Thin", 
    "ExtraLight": "ExtraLight", 
    "Light": "Light",
    "Regular": "Regular", 
    "Medium": "Medium", 
    "SemiBold": "SemiBold", 
    "Bold": "Bold"
}


def clean(font):
    for tag in ["cvt ", "fpgm", "prep", "gasp", "vhea", "vmtx", "VORG", "BASE"]:
        if tag in font: del font[tag]

def fix_meta(font, family_name, weight_name, is_italic, is_wide, avg_width):
    is_bold_style = (weight_name == 'Bold')
    is_regular_style = (weight_name == 'Regular')
    
    # PPT 등지에서 italic이 제대로 처리 안되는데... 
    if is_regular_style or is_bold_style:
        legacy_family = family_name
        if is_regular_style: legacy_subfamily = 'Italic' if is_italic else 'Regular'
        else: legacy_subfamily = 'Bold Italic' if is_italic else 'Bold'
    else:
        legacy_family = f"{family_name} {weight_name}"
        legacy_subfamily = 'Italic' if is_italic else 'Regular'
        
    typo_family = family_name
    typo_subfamily = weight_name
    if is_italic and weight_name == 'Regular': typo_subfamily = 'Italic'
    elif is_italic: typo_subfamily += ' Italic'

    clean_family = family_name.replace(" ", "")
    clean_sub = typo_subfamily.replace(" ", "")
    ps_name = f"{clean_family}-{clean_sub}"
    unique_id = f"1.000;MYRT;{ps_name}"

    replace_map = {
        1: legacy_family, 
        2: legacy_subfamily, 
        3: unique_id, 
        4: f"{family_name} {typo_subfamily}",
        5: f"Version {FONT_VERSION}",
        6 : ps_name
    }

    if (legacy_family != typo_family) or (legacy_subfamily != typo_subfamily):
        replace_map[16] = typo_family
        replace_map[17] = typo_subfamily

    font['name'].names = [n for n in font['name'].names if n.nameID not in [1, 2, 3, 4, 6, 16, 17, 21, 22]]
    
    for nid, string in replace_map.items():
        font['name'].setName(string, nid, 3, 1, 1033)
        font['name'].setName(string, nid, 1, 0, 0)

    # 뭔가 시스템에서 이탤릭을 이상하게 인식해서 고친 흔적
    fs_sel = 0
    if "Bold" in weight_name: fs_sel |= (1 << 5)
    if is_italic: fs_sel |= (1 << 0)
    if not is_italic and weight_name == "Regular": fs_sel |= (1 << 6)
    font['OS/2'].fsSelection = fs_sel

    mac_style = 0
    if "Bold" in weight_name: mac_style |= (1 << 0)
    if is_italic: mac_style |= (1 << 1)
    font['head'].macStyle = mac_style
    font['head'].fontRevision = float(FONT_VERSION)

    font['OS/2'].usWidthClass = 5
    if is_wide:
        font['OS/2'].panose.bProportion = 3
        font['post'].isFixedPitch = 0
    else:
        font['OS/2'].panose.bProportion = 9
        font['post'].isFixedPitch = 1

    font['OS/2'].ulCodePageRange1 |= (1 << 19)
    font['OS/2'].xAvgCharWidth = avg_width

def condense_font_x(font, scale_x):
    # x방향 shrink
    hmtx = font['hmtx']
    glyf = font['glyf']
    glyph_set = font.getGlyphSet()

    for glyph_name in list(glyf.keys()):
        width, lsb = hmtx[glyph_name]
        new_width = int(width * scale_x)

        glyph = glyf.get(glyph_name)
        if glyph and getattr(glyph, 'numberOfContours', 0) != 0:
            matrix = (scale_x, 0, 0, 1.0, 0, 0)
            pen = TTGlyphPen(glyph_set)
            transform_pen = TransformPen(pen, matrix)
            glyph.draw(transform_pen, glyf)
            
            new_glyph = pen.glyph()
            new_glyph.recalcBounds(glyf)
            
            glyf[glyph_name] = new_glyph
            hmtx[glyph_name] = (new_width, int(lsb * scale_x))
        else:
            hmtx[glyph_name] = (new_width, int(lsb * scale_x))

def scale_kr(kr_font, target_width, is_italic=False):
    hmtx = kr_font['hmtx']
    glyf = kr_font['glyf']
    cmap = kr_font.getBestCmap()
    glyph_set = kr_font.getGlyphSet()

    scale_factor = min(target_width / 892.0, 1.1)
    # 대충 재보니까 9도쯤 돼서 tan 9 \simeq 0.1583
    slant_x = 0.1583 if is_italic else 0.0

    for codepoint, glyph_name in cmap.items():
        is_korean_range = (
            (0xAC00 <= codepoint <= 0xD7A3) or (0x3130 <= codepoint <= 0x318F) or
            (0x1100 <= codepoint <= 0x11FF) or (0xFF00 <= codepoint <= 0xFFEF) or
            (0x3000 <= codepoint <= 0x303F)
        )
        if not is_korean_range: continue

        glyph = glyf.get(glyph_name)
        if glyph and getattr(glyph, 'numberOfContours', 0) != 0:
            matrix = (scale_factor, 0, slant_x * scale_factor, scale_factor, 0, 0)
            pen1 = TTGlyphPen(glyph_set)
            transform_pen1 = TransformPen(pen1, matrix)
            glyph.draw(transform_pen1, glyf)

            temp_glyph = pen1.glyph()
            temp_glyph.recalcBounds(glyf)

            glyph_real_width = temp_glyph.xMax - temp_glyph.xMin
            new_lsb = int((target_width - glyph_real_width) / 2)

            shift_x = new_lsb - temp_glyph.xMin
            shift_matrix = (1, 0, 0, 1, shift_x, 0)

            pen2 = TTGlyphPen(glyph_set)
            transform_pen2 = TransformPen(pen2, shift_matrix)
            temp_glyph.draw(transform_pen2, glyf)

            final_glyph = pen2.glyph()
            final_glyph.recalcBounds(glyf)

            glyf[glyph_name] = final_glyph
            hmtx[glyph_name] = (target_width, new_lsb)
        else:
            hmtx[glyph_name] = (target_width, 0)

def enablecjk(font):
    for table_tag in ['GSUB', 'GPOS']:
        if table_tag not in font: continue
        
        table = font[table_tag].table
        if not hasattr(table, 'ScriptList') or not table.ScriptList: continue

        script_records = table.ScriptList.ScriptRecord
        feature_list = table.FeatureList.FeatureRecord

        if table_tag == 'GSUB':
            calt_record = next((fr for fr in feature_list if fr.FeatureTag == 'calt'), None)
            liga_record = next((fr for fr in feature_list if fr.FeatureTag == 'liga'), None)
            
            if calt_record and not liga_record:
                new_liga = copy.deepcopy(calt_record)
                new_liga.FeatureTag = 'liga'
                feature_list.append(new_liga)
                table.FeatureList.FeatureCount = len(feature_list)

        source_record = next((r for r in script_records if r.ScriptTag == 'latn'), None)
        if not source_record:
            source_record = next((r for r in script_records if r.ScriptTag == 'DFLT'), None)
        if not source_record: continue

        target_feature_indices = []
        for i, fr in enumerate(feature_list):
            if table_tag == 'GSUB' and fr.FeatureTag in ['calt', 'liga', 'dlig']:
                target_feature_indices.append(i)
            elif table_tag == 'GPOS' and fr.FeatureTag in ['calt', 'kern', 'mark', 'mkmk', 'curs']:
                target_feature_indices.append(i)

        if source_record.Script.DefaultLangSys:
            for idx in target_feature_indices:
                if idx not in source_record.Script.DefaultLangSys.FeatureIndex:
                    source_record.Script.DefaultLangSys.FeatureIndex.append(idx)
                    source_record.Script.DefaultLangSys.FeatureCount += 1

        target_tags = ['hang', 'hani', 'kana', 'hira', 'jamo']
        existing_tags = {r.ScriptTag: r for r in script_records}
        
        for tag in target_tags:
            if tag not in existing_tags:
                new_record = ot.ScriptRecord()
                new_record.ScriptTag = tag
                new_record.Script = ot.Script()
                new_record.Script.DefaultLangSys = copy.deepcopy(source_record.Script.DefaultLangSys)
                new_record.Script.LangSysRecord = []
                new_record.Script.LangSysCount = 0
                
                if tag == 'hang':
                    lang_sys_record = ot.LangSysRecord()
                    lang_sys_record.LangSysTag = 'KOR '
                    lang_sys_record.LangSys = copy.deepcopy(source_record.Script.DefaultLangSys)
                    new_record.Script.LangSysRecord.append(lang_sys_record)
                    new_record.Script.LangSysCount = 1

                script_records.append(new_record)
            else:
                record = existing_tags[tag]
                if not record.Script.DefaultLangSys:
                    record.Script.DefaultLangSys = copy.deepcopy(source_record.Script.DefaultLangSys)
                else:
                    for idx in target_feature_indices:
                        if idx not in record.Script.DefaultLangSys.FeatureIndex:
                            record.Script.DefaultLangSys.FeatureIndex.append(idx)
                            record.Script.DefaultLangSys.FeatureCount += 1

        script_records.sort(key=lambda r: r.ScriptTag)
        table.ScriptList.ScriptCount = len(script_records)

def build_variant(latin_path, kr_path, weight_key, is_italic, is_wide, latin_target_width, kr_target_width, family_name, out_filename):
    latin_font = TTFont(latin_path)
    kr_font = TTFont(kr_path)

    backup_tables = {}
    for tag in ["cvt ", "fpgm", "prep", "gasp"]:
        if tag in latin_font:
            backup_tables[tag] = copy.deepcopy(latin_font[tag])

    clean(latin_font)
    clean(kr_font)
    
    for tag in ["GSUB", "GPOS", "GDEF"]:
        if tag in kr_font: del kr_font[tag]

    if latin_target_width != 600:
        condense_font_x(latin_font, latin_target_width / 600.0)

    scale_kr(kr_font, kr_target_width, is_italic=is_italic)

    temp_latin = f"temp_latin_{out_filename}"
    temp_kr = f"temp_kr_{out_filename}"
    latin_font.save(temp_latin)
    kr_font.save(temp_kr)

    merged = Merger().merge([temp_latin, temp_kr])

    fix_meta(merged, family_name, weight_key, is_italic, is_wide, avg_width=latin_target_width)

    for tag, table_data in backup_tables.items(): merged[tag] = table_data

    enablecjk(merged)

    if 'GDEF' in merged and hasattr(merged['GDEF'].table, 'GlyphClassDef') and merged['GDEF'].table.GlyphClassDef:
        gdef_class = merged['GDEF'].table.GlyphClassDef.classDefs
        cmap = merged.getBestCmap()
        for codepoint, glyph_name in cmap.items():
            is_cjk = (
                (0xAC00 <= codepoint <= 0xD7A3) or (0x3130 <= codepoint <= 0x318F) or
                (0x1100 <= codepoint <= 0x11FF) or (0x4E00 <= codepoint <= 0x9FFF) or
                (0x3000 <= codepoint <= 0x303F)
            )
            if is_cjk and glyph_name not in gdef_class:
                gdef_class[glyph_name] = 1

    dir_path = os.path.join(OUTPUT_DIR, family_name)
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)

    merged.save(os.path.join(dir_path, out_filename))

    for tmp in [temp_latin, temp_kr]:
        if os.path.exists(tmp): os.remove(tmp)

def merge_all():
    if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)

    files = sorted([f for f in os.listdir(LATIN_DIR) if f.endswith(".ttf")])
    for f in files:
        weight_key = next((w for w in WEIGHT_MAP if w in f), "Regular")
        is_italic = "Italic" in f

        latin_path = os.path.join(LATIN_DIR, f)
        kr_path = os.path.join(KR_DIR, f"IBMPlexSansKR-{WEIGHT_MAP[weight_key]}.ttf")

        if not os.path.exists(kr_path): continue
        print(f"Working: {f}")

        try:
            out_std = f.replace("Lilex", "LilexKRStd")
            build_variant(latin_path, kr_path, weight_key, is_italic, False, 600, 1200, NEW_FAMILY_NAME_STD, out_std)
            print(f"OK {out_std}")

            out_compact = f.replace("Lilex", "LilexKRCompact")
            build_variant(latin_path, kr_path, weight_key, is_italic, False, 528, 1056, NEW_FAMILY_NAME_COMPACT, out_std)
            print(f"OK {out_compact}")

            out_wide = f.replace("Lilex", "LilexKR35")
            build_variant(latin_path, kr_path, weight_key, is_italic, True, 600, 1000, NEW_FAMILY_NAME_WIDE, out_wide)
            print(f"OK {out_wide}")

        except Exception as e:
            print(f"Error {e}")

if __name__ == "__main__":
    merge_all()