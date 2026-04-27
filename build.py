#!/bin/env python3

import io
import os
import shutil
import copy
import math
import concurrent.futures
from fontTools.ttLib import TTFont
from fontTools.merge import Merger
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.subset import Subsetter, Options
from fontTools.ttLib.tables import otTables
from ttfautohint import ttfautohint

FONT_VERSION="1.005"

LATIN_DIR = "./source/Lilex"
LATIN_FILENAME = "Lilex-{style}.ttf"

KR_DIR = "./source/IBM_Plex_Sans_KR"
KR_FILENAME = "IBMPlexSansKR-{style}.ttf"

OUTPUT_DIR = "./output"
OUTPUT_FILENAME = "{filename}-{style}.ttf"

WEIGHT_MAP = {
    "Thin": "Thin", 
    "ExtraLight": "ExtraLight", 
    "Light": "Light",
    "Regular": "Regular", 
    "Medium": "Medium", 
    "SemiBold": "SemiBold", 
    "Bold": "Bold"
}

def get_latin_font(weight, is_italic):
    path = os.path.join(LATIN_DIR, LATIN_FILENAME.format(
        style = f"{(weight != 'Regular' or not is_italic) and weight or ''}{is_italic and 'Italic' or ''}"
    ))
    return TTFont(path)

def get_kr_font(weight):
    path = os.path.join(KR_DIR, KR_FILENAME.format(
        style = weight
    ))
    return TTFont(path)

def clean(font):
    for tag in ["cvt ", "fpgm", "prep", "gasp", "vhea", "vmtx", "VORG", "BASE"]:
        if tag in font: del font[tag]

def filter_kr(font):
    options = Options()
    options.layout_features = ["*"]
    options.name_IDs = ["*"]
    
    subsetter = Subsetter(options=options)
    
    korean_unicodes = set(
        list(range(0xAC00, 0xD7A4)) +
        list(range(0x3130, 0x3190)) +
        list(range(0x1100, 0x1200)) +
        list(range(0xFF00, 0xFFF0)) +
        list(range(0x3000, 0x3040))
    )
    
    subsetter.populate(unicodes=korean_unicodes)
    subsetter.subset(font)

def fix_meta(font, family_name, weight_name, is_italic, is_wide, avg_width):
    is_bold_style = (weight_name == 'Bold')
    is_regular_style = (weight_name == 'Regular')
    
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
    unique_id = f"{FONT_VERSION};MYRT;{ps_name}"

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

    fs_sel = 0
    if "Bold" in weight_name: fs_sel |= (1 << 5)
    if is_italic: fs_sel |= (1 << 0)
    if not is_italic and weight_name == "Regular": fs_sel |= (1 << 6)
    fs_sel |= (1 << 7)
    font['OS/2'].fsSelection = fs_sel
    
    if font['OS/2'].version < 4:
        font['OS/2'].version = 4

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

def adjust_latin(font, base_width, target_glyph_width, target_advance_width, scale_y):
    hmtx = font['hmtx']
    glyf = font['glyf']
    glyph_set = font.getGlyphSet()

    glyph_scale_x = target_glyph_width / base_width
    advance_scale_x = target_advance_width / base_width

    new_glyf_data = {}
    new_hmtx_data = {}

    for glyph_name in list(glyf.keys()):
        if glyph_name not in hmtx.metrics: continue
        w, lsb = hmtx.metrics[glyph_name]
        new_w = int(w * advance_scale_x)

        glyph = glyf.get(glyph_name)
        if glyph and getattr(glyph, 'numberOfContours', 0) != 0:
            rec_pen = DecomposingRecordingPen(glyph_set)
            glyph.draw(rec_pen, glyf)

            transform_matrix = (glyph_scale_x, 0, 0, scale_y, 0, 0)
            pen_step1 = TTGlyphPen(glyph_set)
            t_pen1 = TransformPen(pen_step1, transform_matrix)
            rec_pen.replay(t_pen1)

            temp_glyph = pen_step1.glyph()
            temp_glyph.recalcBounds(glyf)

            scaled_w_original = w * glyph_scale_x
            scaled_lsb = lsb * glyph_scale_x

            extra_padding = new_w - scaled_w_original
            target_lsb = int(scaled_lsb + (extra_padding / 2))

            shift_x = target_lsb - temp_glyph.xMin

            translate_matrix = (1, 0, 0, 1, shift_x, 0)
            pen_step2 = TTGlyphPen(glyph_set)
            t_pen2 = TransformPen(pen_step2, translate_matrix)
            temp_glyph.draw(t_pen2, glyf)

            final_glyph = pen_step2.glyph()
            final_glyph.recalcBounds(glyf)

            new_glyf_data[glyph_name] = final_glyph
            new_hmtx_data[glyph_name] = (new_w, target_lsb)
        else:
            new_hmtx_data[glyph_name] = (new_w, int(lsb * advance_scale_x))

    for g_name, g_data in new_glyf_data.items():
        glyf[g_name] = g_data
        
    hmtx.metrics.update(new_hmtx_data)

def adjust_kr(font, target_font, target_width, target_upm, slant_degree, boost_ratio, baseline_char_latin, baseline_char_kr):
    hmtx = font['hmtx']
    glyf = font['glyf']
    cmap = font.getBestCmap()
    glyph_set = font.getGlyphSet()

    t_cmap = target_font.getBestCmap()
    t_glyph_set = target_font.getGlyphSet()
    
    latin_name = t_cmap.get(ord(baseline_char_latin))
    pen_t = BoundsPen(t_glyph_set)
    t_glyph_set[latin_name].draw(pen_t)
    t_ymin, t_ymax = pen_t.bounds[1], pen_t.bounds[3]
    t_height = t_ymax - t_ymin

    kr_name = cmap.get(ord(baseline_char_kr))
    pen_s = BoundsPen(glyph_set)
    glyph_set[kr_name].draw(pen_s)
    s_ymin, s_ymax = pen_s.bounds[1], pen_s.bounds[3]
    s_height = s_ymax - s_ymin

    base_scale = t_height / s_height
    uniform_scale = base_scale * boost_ratio

    target_ymin = t_ymin - (t_height * 0.00)
    shift_y = target_ymin - (s_ymin * uniform_scale)
    
    slant_x = math.tan(slant_degree * 3.1416 / 180.0)

    new_glyf_data = {}
    new_hmtx_data = {}

    for codepoint, glyph_name in cmap.items():
        if not (
            (0xAC00 <= codepoint <= 0xD7A3) or (0x3130 <= codepoint <= 0x318F) or
            (0x1100 <= codepoint <= 0x11FF) or (0xFF00 <= codepoint <= 0xFFEF) or
            (0x3000 <= codepoint <= 0x303F)
        ): continue

        glyph = glyf.get(glyph_name)
        
        if not glyph or getattr(glyph, 'numberOfContours', 0) == 0:
            new_hmtx_data[glyph_name] = (target_width, 0)
            continue

        w, lsb = hmtx[glyph_name]

        rec_pen = DecomposingRecordingPen(glyph_set)
        glyph.draw(rec_pen, glyf)

        transform_matrix = (uniform_scale, 0, slant_x * uniform_scale, uniform_scale, 0, shift_y)
        
        pen_step1 = TTGlyphPen(glyph_set)
        t_pen1 = TransformPen(pen_step1, transform_matrix)
        rec_pen.replay(t_pen1)
        
        temp_glyph = pen_step1.glyph()
        temp_glyph.recalcBounds(glyf)

        scaled_w = w * uniform_scale
        scaled_lsb = lsb * uniform_scale
        
        extra_padding = target_width - scaled_w
        target_lsb = int(scaled_lsb + (extra_padding / 2))
        
        shift_x = target_lsb - temp_glyph.xMin

        translate_matrix = (1, 0, 0, 1, shift_x, 0)
        
        pen_step2 = TTGlyphPen(glyph_set)
        t_pen2 = TransformPen(pen_step2, translate_matrix)
        temp_glyph.draw(t_pen2, glyf)
        
        final_glyph = pen_step2.glyph()
        final_glyph.recalcBounds(glyf)

        new_glyf_data[glyph_name] = final_glyph
        new_hmtx_data[glyph_name] = (target_width, target_lsb)

    for g_name, g_data in new_glyf_data.items():
        glyf[g_name] = g_data
        
    for h_name, h_data in new_hmtx_data.items():
        hmtx[h_name] = h_data

    font['head'].unitsPerEm = target_upm
    

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
                new_record = otTables.ScriptRecord()
                new_record.ScriptTag = tag
                new_record.Script = otTables.Script()
                new_record.Script.DefaultLangSys = copy.deepcopy(source_record.Script.DefaultLangSys)
                new_record.Script.LangSysRecord = []
                new_record.Script.LangSysCount = 0
                
                if tag == 'hang':
                    lang_sys_record = otTables.LangSysRecord()
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

def build_variant(latin_font, kr_font, weight_key, is_italic, is_wide, latin_target_width, kr_target_width, slant_degree, family_name):
    latin_cmap = latin_font.getBestCmap()
    latin_basewidth,_ = latin_font['hmtx'][latin_cmap.get(ord('a'))]
    latin_upm = latin_font['head'].unitsPerEm

    style = f"{(weight_key != 'Regular' or not is_italic) and weight_key or ''}{is_italic and 'Italic' or ''}"
    out_filename = OUTPUT_FILENAME.format_map({"filename": family_name.replace(' ', ''), "style": style})
    print(f"Working: {out_filename}")

    buffer0 = io.BytesIO()
    buffer1 = io.BytesIO()

    latin_font.save(buffer0)

    latin_metrics = copy.deepcopy(latin_font['OS/2'])
    latin_hhea = copy.deepcopy(latin_font['hhea'])

    clean(latin_font)
    clean(kr_font)
    
    adjust_latin(latin_font, latin_basewidth, latin_basewidth*0.6+latin_target_width*0.4, latin_target_width, 0.985)
    adjust_kr(kr_font, latin_font, kr_target_width, latin_upm, is_italic*slant_degree, 1.05 / 0.985, 'X', '모')
    filter_kr(kr_font)

    latin_font.save(buffer1)

    hinted = ttfautohint(
        in_buffer=buffer1.getvalue(),
        windows_compatibility=False,
        symbol=False,
        increase_x_height=14,
        gray_stem_width_mode=0,
        gdi_cleartype_stem_width_mode=0,
        dw_cleartype_stem_width_mode=0
    )

    buffer0.seek(0)
    buffer1.seek(0)

    buffer0.write(hinted)
    kr_font.save(buffer1)

    buffer0.seek(0)
    buffer1.seek(0)

    merged = Merger().merge([buffer0, buffer1])

    buffer0.close()
    buffer1.close()

    merged['OS/2'].sTypoAscender = latin_metrics.sTypoAscender
    merged['OS/2'].sTypoDescender = latin_metrics.sTypoDescender
    merged['OS/2'].sTypoLineGap = latin_metrics.sTypoLineGap
    merged['OS/2'].usWinAscent = latin_metrics.usWinAscent
    merged['OS/2'].usWinDescent = latin_metrics.usWinDescent
    merged['hhea'].ascent = latin_hhea.ascent
    merged['hhea'].descent = latin_hhea.descent
    merged['hhea'].lineGap = latin_hhea.lineGap

    fix_meta(merged, family_name, weight_key, is_italic, is_wide, latin_target_width)
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

    dir_path = os.path.join('output', family_name)
    all_path = 'output/all'
    if not os.path.exists(dir_path): os.makedirs(dir_path, exist_ok=True)
    if not os.path.exists(all_path): os.makedirs(all_path, exist_ok=True)
    
    merged.save(os.path.join(dir_path, out_filename))
    shutil.copyfile(os.path.join(dir_path, out_filename), os.path.join(all_path, out_filename))

    latin_font.close()
    kr_font.close()
    merged.close()

import traceback
def _worker_build(task):
    weight = task['weight']
    is_italic = task['is_italic']
    family_name = task['family_name']
    is_wide = task['is_wide']
    latin_target_width = task['latin_target_width']
    kr_target_width = task['kr_target_width']

    latin_font = get_latin_font(weight, is_italic)
    kr_font = get_kr_font(weight)

    try:
        build_variant(
            latin_font=latin_font,
            kr_font=kr_font,
            weight_key=weight,
            is_italic=is_italic,
            is_wide=is_wide,
            latin_target_width=latin_target_width,
            kr_target_width=kr_target_width,
            slant_degree=8.5,
            family_name=family_name
        )

    except Exception:
        traceback.print_exc()  

def merge_all(regular_only=False):
    if os.path.exists(OUTPUT_DIR): shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR)

    tasks = []
    styles = ((i,j) for i in WEIGHT_MAP.keys() for j in [False, True])
    
    for (weight,is_italic) in styles:
        tasks.append({
            'weight': weight, 'is_italic': is_italic,
            'family_name': f'LilexKR Std',
            'is_wide': False, 'latin_target_width': 600, 'kr_target_width': 1200
        })
        
        tasks.append({
            'weight': weight, 'is_italic': is_italic,
            'family_name': f'LilexKR 528',
            'is_wide': True, 'latin_target_width': 528, 'kr_target_width': 1056
        })
        
        tasks.append({
            'weight': weight, 'is_italic': is_italic,
            'family_name': f'LilexKR 35',
            'is_wide': True, 'latin_target_width': 600, 'kr_target_width': 1000
        })

    with concurrent.futures.ProcessPoolExecutor() as executor:
        executor.map(_worker_build, tasks)
        
        
if __name__ == "__main__":
    merge_all(False)
    