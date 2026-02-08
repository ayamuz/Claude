---
name: accme-provider-scraper
description: |
  Scrape the complete ACCME Provider Directory (https://accme.org/cme-provider-directory/)
  and build a structured Excel spreadsheet with priority tiers, Spanish market flagging,
  and high-volume analysis columns. Use this skill whenever the user mentions ACCME,
  CME providers, CME provider directory, accredited CME organizations, continuing medical
  education providers, or wants to build a prospecting list of medical education providers.
  Also trigger when the user asks to "refresh" or "update" their CME provider data.
---

# ACCME Provider Directory Scraper

Extracts all accredited CME provider records from the ACCME Provider Directory and
compiles them into a professional Excel workbook with business intelligence columns
for outreach prioritization.

## Overview

The ACCME directory is powered by WordPress and exposes a REST API at:
`https://accme.org/wp-json/wp/v2/provider`

This API returns up to 100 records per page. The directory currently has ~1,449 providers
(check `X-WP-Total` header for current count). The data includes provider name, location,
accreditation details, contact information, activity counts, and more.

**Important constraint**: The VM cannot make direct HTTP requests to external sites (proxy
block returns 403). All data fetching must happen via browser JavaScript tools, then
transferred to the VM for processing.

## Step-by-Step Workflow

### Phase 1: Fetch Data via Browser

1. **Get browser tab context** using `tabs_context_mcp`, then create a new tab with `tabs_create_mcp`.

2. **Navigate** to `https://accme.org/wp-json/wp/v2/provider?per_page=1&page=1` to confirm the API works.

3. **Run the bulk fetch script** via `javascript_tool`. This fetches all pages and builds a compact tilde-delimited dataset:

```javascript
(async () => {
  const base = 'https://accme.org/wp-json/wp/v2/provider';
  let page = 1, all = [], total = null;
  while (true) {
    const resp = await fetch(`${base}?per_page=100&page=${page}`);
    if (!resp.ok) break;
    if (total === null) total = parseInt(resp.headers.get('X-WP-Total'));
    const data = await resp.json();
    if (!data.length) break;
    all = all.concat(data);
    page++;
    if (all.length >= total) break;
  }

  // Build compact tilde-delimited lines (16 fields per record)
  // Fields: name~city~state~country~website~accType~accStatus~jointProv~activities~contactName~contactPhone~address~zip~formats~accreditedBy~providerId
  const accTypeMap = {
    'accme_accredited_provider': 'A',
    'jointly_accredited_provider': 'J',
    'state_accredited_provider': 'S'
  };
  const accStatusMap = {
    'accreditation_with_commendation': 'C',
    'accreditation': 'A',
    'provisional_accreditation': 'P',
    'probation': 'X',
    'joint_accreditation': 'JA',
    'joint_accreditation_with_commendation': 'JC'
  };

  // Fetch taxonomy terms for lookups
  const fetchTerms = async (taxonomy) => {
    const map = {};
    let pg = 1;
    while (true) {
      const r = await fetch(`${base.replace('/provider','')}/${taxonomy}?per_page=100&page=${pg}`);
      if (!r.ok) break;
      const terms = await r.json();
      if (!terms.length) break;
      terms.forEach(t => map[t.id] = t.slug);
      pg++;
    }
    return map;
  };

  const [statusTerms, typeTerms, formatTerms, jpTerms] = await Promise.all([
    fetchTerms('accreditation_status'),
    fetchTerms('provider_type'),
    fetchTerms('activity_format'),
    fetchTerms('joint_providership')
  ]);

  const lines = all.map(p => {
    const name = (p.title?.rendered || '').replace(/&amp;/g,'&').replace(/&#8211;/g,'–').replace(/&#8217;/g,"'").replace(/~/g,'-');
    const meta = p.meta || {};
    const city = (meta.city || '').replace(/~/g,'-');
    const state = (meta.state || '').replace(/~/g,'-');
    const country = meta.country || 'USA';
    const website = (meta.website || '').replace(/~/g,'-');
    const contact = (meta.contact_name || '').replace(/~/g,'-');
    const phone = (meta.contact_phone || '').replace(/~/g,'-');
    const address = (meta.street_address || '').replace(/~/g,'-');
    const zip = (meta.zip || '').replace(/~/g,'-');
    const activities = meta.number_of_activities || 0;

    const typeIds = p.provider_type || [];
    const typeSlugs = typeIds.map(id => typeTerms[id] || '').filter(Boolean);
    const accType = typeSlugs.map(s => accTypeMap[s] || 'O').join(',') || 'O';

    const statusIds = p.accreditation_status || [];
    const statusSlugs = statusIds.map(id => statusTerms[id] || '').filter(Boolean);
    const accStatus = statusSlugs.map(s => accStatusMap[s] || 'O').join(',') || 'O';

    const formatIds = p.activity_format || [];
    const formats = formatIds.map(id => {
      const slug = formatTerms[id] || '';
      return slug.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
    }).filter(Boolean).join(', ');

    const jpIds = p.joint_providership || [];
    const jpSlugs = jpIds.map(id => jpTerms[id] || '');
    const jp = jpSlugs.includes('yes') ? 'Y' : 'N';

    const accBy = (meta.accredited_by || '').replace(/~/g,'-');
    const providerId = p.id;

    return [name, city, state, country, website, accType, accStatus, jp,
            activities, contact, phone, address, zip, formats, accBy, providerId].join('~');
  });

  // Sort by activities descending
  lines.sort((a, b) => {
    const aAct = parseInt(a.split('~')[8]) || 0;
    const bAct = parseInt(b.split('~')[8]) || 0;
    return bAct - aAct;
  });

  // Split into parts of ~182 records each (to stay under get_page_text limits)
  const partSize = 182;
  window._parts = [];
  for (let i = 0; i < lines.length; i += partSize) {
    window._parts.push(lines.slice(i, i + partSize));
  }

  return `Fetched ${all.length} providers, created ${window._parts.length} parts (${window._parts.map(p=>p.length).join(', ')} records each)`;
})();
```

Wait for this to complete. It may take 30-60 seconds.

### Phase 2: Transfer Data to VM

For each part (0 through N-1), repeat this cycle:

1. **Load part into DOM** via `javascript_tool`:
```javascript
var text = window._parts[N].join('\n');
document.body.innerHTML = '<article>' + text.replace(/</g,'&lt;').replace(/>/g,'&gt;') + '</article>';
'Part N loaded: ' + text.length + ' chars';
```

2. **Read the text** using `get_page_text` tool on the same tab.

3. **Save to VM** as `partN_joined.txt` (the text comes back space-joined because `get_page_text` joins lines with spaces).

4. **Split records** using the bundled `scripts/split_records.py`:
```bash
python scripts/split_records.py partN_joined.txt partN.txt
```

5. **Concatenate all parts** when done:
```bash
cat part0.txt part1.txt ... partN.txt > providers_raw.jsonl
```

### Phase 3: Build Excel

Run the bundled `scripts/build_excel.py` to generate the final spreadsheet:

```bash
python scripts/build_excel.py providers_raw.jsonl output.xlsx
```

This creates a workbook with 5 sheets:
- **All Providers** — Complete dataset sorted by tier then activities (26 columns)
- **Tier 1 Targets** — High-priority prospects (100+ activities, Commendation, PR, Spanish-market cities)
- **Mental Health Targets** — Providers matching mental health keywords (purple header), sorted by tier/activities
- **Spanish Market Focus** — Providers in PR or Spanish-market cities (Miami, San Antonio, LA, Phoenix, El Paso, Tucson, Albuquerque)
- **High Volume** — Providers with 100+ activities/year

### Mental Health Enrichment Columns

The build script adds 5 enrichment columns to every record:
- **MH Relevance** — "Yes" if provider name or accredited_by matches any mental health keyword
- **Specialty Category** — Matching categories (e.g., "Psychiatry", "Neurology, Substance Use")
- **Org Type** — Professional Society, Academic Medical Center, Hospital/Health System, Government/Public Health, Education/CME Company, or Other
- **Global Footprint** — "Yes" if non-US country or name contains international/global/world
- **Pitch Angle** — Auto-generated outreach angle combining specialty, Spanish market, global scope, and volume

Mental health keyword categories: Psychiatry, Mental Health, Neurology, Substance Use, Psychology, Dementia/Cognitive, Child/Adolescent, Trauma/Crisis, Sleep Medicine, Palliative/Hospice, Simulation, Neurodiversity.

### Phase 4: Quality Checks

Verify the output:
- Record count matches expected total (~1,449)
- No duplicate provider IDs (same-name orgs in different locations are OK)
- Tier distribution is reasonable (expect ~40% Tier 1, ~38% Tier 2, ~22% Tier 3)
- Spanish Market sheet only contains qualifying locations
- High Volume sheet only contains activities >= 100
- Mental Health Targets sheet only contains MH Relevance = "Yes"
- Accreditation codes are expanded to full text

## Data Format

Each record has 16 tilde-delimited fields:

| # | Field | Example |
|---|-------|---------|
| 0 | Provider Name | University of Utah School of Medicine |
| 1 | City | Salt Lake City |
| 2 | State | UT |
| 3 | Country | USA |
| 4 | Website | http://medicine.utah.edu/cme |
| 5 | Accreditation Type | A (ACCME), J (Joint), S (State) |
| 6 | Accreditation Status | C (Commendation), A (Accredited), P (Provisional), X (Probation), JA, JC |
| 7 | Joint Providership | Y or N |
| 8 | Activities/Year | 264 |
| 9 | Contact Name | Marci Fjelstad |
| 10 | Contact Phone | (801) 703-5295 |
| 11 | Address | 27 S Mario Capecchi Dr. |
| 12 | ZIP | 84113 |
| 13 | Activity Formats | Enduring Material, Live Course, etc. |
| 14 | Accredited By | ACCME, Joint Accreditation, state society name |
| 15 | Provider ID | 334 |

## Priority Tier Logic

- **Tier 1**: activities >= 100, OR has Commendation status, OR state == PR, OR city is a Spanish-market city
- **Tier 2**: activities >= 20, OR ACCME Accredited type, OR name contains Medical Society/Association/Academy/College
- **Tier 3**: Everything else

## Troubleshooting

- **API returns 403**: The WP REST API may have rate limiting. Add delays between page fetches.
- **get_page_text truncates**: Keep part sizes at ~182 records. If the text exceeds ~50K chars, reduce part size.
- **Split records produces wrong field count**: Check for tildes within data fields (they should be replaced with hyphens during fetch).
- **VM cannot fetch URLs**: This is expected. All HTTP requests must go through browser JavaScript tools.
