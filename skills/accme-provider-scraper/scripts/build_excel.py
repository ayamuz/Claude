"""Build structured Excel workbook from ACCME provider data.

Reads tilde-delimited provider records and creates a professional Excel
workbook with 4 sheets: All Providers, Tier 1 Targets, Spanish Market Focus,
and High Volume.

Usage:
    python build_excel.py <input_data.txt> <output.xlsx>

Input format: One record per line, 16 tilde-delimited fields.
See SKILL.md for field definitions.
"""
import sys, html as htmlmod
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

SPANISH_CITIES = ['miami','san antonio','los angeles','phoenix','el paso','tucson','albuquerque']
COLS = ['Provider Name','City','State','Country','Website','Accreditation Type',
        'Accreditation Status','Joint Providership','Activities/Year','Contact Name',
        'Contact Phone','Address','ZIP','Activity Formats','Accredited By','Provider ID',
        'Priority Tier','Spanish Market','High Volume','Commendation Status','Notes']
COL_WIDTHS = [45,18,6,6,30,25,30,10,12,25,18,40,12,35,30,10,10,14,11,18,20]

ACC_TYPE_MAP = {'A': 'ACCME Accredited', 'J': 'Jointly Accredited', 'S': 'State Accredited'}
ACC_STATUS_MAP = {'C': 'Accreditation with Commendation', 'A': 'Accredited', 'P': 'Provisional',
                  'X': 'Probation', 'JA': 'Joint Accreditation', 'JC': 'Joint with Commendation', 'O': 'Other'}
JP_MAP = {'Y': 'Yes', 'N': 'No'}

def expand_codes(r):
    r['accreditation_type'] = ACC_TYPE_MAP.get(r['accreditation_type'], r['accreditation_type'])
    r['accreditation_status'] = ACC_STATUS_MAP.get(r['accreditation_status'], r['accreditation_status'])
    r['joint_providership'] = JP_MAP.get(r['joint_providership'], r['joint_providership'])

def compute_tier(r):
    activities = r.get('activities', 0)
    status = r.get('accreditation_status', '')
    state = r.get('state', '')
    city = (r.get('city', '') or '').lower()
    name = r.get('provider_name', '')
    acc_type = r.get('accreditation_type', '')
    has_commendation = 'Commendation' in status
    if activities >= 100 or has_commendation or state == 'PR' or city in SPANISH_CITIES:
        return 1
    if (activities >= 20 or acc_type == 'ACCME Accredited' or
        any(kw in name for kw in ['Medical Society','Medical Association','Academy','College'])):
        return 2
    return 3

def build(data_file, output_file):
    records = []
    with open(data_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split('~')
            if len(parts) < 16:
                parts += [''] * (16 - len(parts))
            name = htmlmod.unescape(parts[0])
            activities = 0
            try:
                activities = int(parts[8])
            except:
                pass
            r = {
                'provider_name': name, 'city': parts[1], 'state': parts[2],
                'country': parts[3], 'website': parts[4], 'accreditation_type': parts[5],
                'accreditation_status': parts[6], 'joint_providership': parts[7],
                'activities': activities, 'contact_name': parts[9], 'contact_phone': parts[10],
                'address': parts[11], 'zip': parts[12], 'activity_formats': parts[13],
                'accredited_by': parts[14], 'provider_id': parts[15],
            }
            expand_codes(r)
            tier = compute_tier(r)
            city_lower = (r['city'] or '').lower()
            spanish = 'Yes' if (r['state'] == 'PR' or city_lower in SPANISH_CITIES) else 'No'
            high_vol = 'Yes' if activities >= 100 else 'No'
            commendation = 'Yes' if 'Commendation' in r['accreditation_status'] else 'No'
            r['tier'] = tier
            r['spanish'] = spanish
            r['high_vol'] = high_vol
            r['commendation'] = commendation
            records.append(r)

    records.sort(key=lambda x: (x['tier'], -x['activities']))
    print(f"Total records: {len(records)}")
    t1 = [r for r in records if r['tier'] == 1]
    t2 = [r for r in records if r['tier'] == 2]
    t3 = [r for r in records if r['tier'] == 3]
    print(f"Tier 1: {len(t1)}, Tier 2: {len(t2)}, Tier 3: {len(t3)}")
    spanish_recs = [r for r in records if r['spanish'] == 'Yes']
    high_vol_recs = sorted([r for r in records if r['high_vol'] == 'Yes'], key=lambda x: -x['activities'])
    print(f"Spanish Market: {len(spanish_recs)}, High Volume: {len(high_vol_recs)}")

    wb = Workbook()
    header_font = Font(name='Arial', bold=True, color='FFFFFF', size=11)
    header_fill = PatternFill('solid', fgColor='2F5496')
    header_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
    data_font = Font(name='Arial', size=10)
    thin_border = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9'))
    tier_fills = {1: PatternFill('solid', fgColor='C6EFCE'), 2: PatternFill('solid', fgColor='FFEB9C'), 3: PatternFill('solid', fgColor='FFC7CE')}

    def row_data(r):
        return [r['provider_name'], r['city'], r['state'], r['country'], r['website'],
                r['accreditation_type'], r['accreditation_status'], r['joint_providership'],
                r['activities'], r['contact_name'], r['contact_phone'], r['address'],
                r['zip'], r['activity_formats'], r['accredited_by'], r['provider_id'],
                r['tier'], r['spanish'], r['high_vol'], r['commendation'], '']

    def write_sheet(ws, data, name):
        ws.title = name
        ws.append(COLS)
        for ci in range(1, len(COLS)+1):
            cell = ws.cell(row=1, column=ci)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align
            cell.border = thin_border
        for ri, r in enumerate(data, start=2):
            rd = row_data(r)
            for ci, val in enumerate(rd, start=1):
                cell = ws.cell(row=ri, column=ci, value=val)
                cell.font = data_font
                cell.border = thin_border
                if ci == 17:
                    cell.fill = tier_fills.get(val, PatternFill())
                    cell.alignment = Alignment(horizontal='center')
                if ci == 9:
                    cell.alignment = Alignment(horizontal='right')
                    cell.number_format = '#,##0'
        for ci, w in enumerate(COL_WIDTHS, start=1):
            ws.column_dimensions[get_column_letter(ci)].width = w
        ws.auto_filter.ref = ws.dimensions
        ws.freeze_panes = 'A2'

    write_sheet(wb.active, records, 'All Providers')
    ws2 = wb.create_sheet()
    write_sheet(ws2, t1, 'Tier 1 Targets')
    ws3 = wb.create_sheet()
    write_sheet(ws3, spanish_recs, 'Spanish Market Focus')
    ws4 = wb.create_sheet()
    write_sheet(ws4, high_vol_recs, 'High Volume')

    wb.save(output_file)
    print(f"Saved to {output_file}")

    # Print stats
    states = {}
    for r in records:
        s = r['state'] or 'Unknown'
        states[s] = states.get(s, 0) + 1
    top_states = sorted(states.items(), key=lambda x: -x[1])[:10]
    print("\nTop 10 states:")
    for s, c in top_states:
        print(f"  {s}: {c}")

    acc_types = {}
    for r in records:
        t = r['accreditation_type'] or 'Unknown'
        acc_types[t] = acc_types.get(t, 0) + 1
    print("\nBy accreditation type:")
    for t, c in sorted(acc_types.items(), key=lambda x: -x[1]):
        print(f"  {t}: {c}")

    with_contact = sum(1 for r in records if r['contact_name'])
    with_website = sum(1 for r in records if r['website'])
    print(f"\nData completeness:")
    print(f"  Contact names: {with_contact}/{len(records)} ({100*with_contact//len(records)}%)")
    print(f"  Websites: {with_website}/{len(records)} ({100*with_website//len(records)}%)")

if __name__ == '__main__':
    data_file = sys.argv[1]
    output_file = sys.argv[2]
    build(data_file, output_file)
