# SpeakSeed data-source audit

Audit date: **2026-10-23**
Scope: licensing and technical suitability for a public, potentially commercial SpeakSeed website. This is an engineering provenance review, not independent legal advice.

## Decision rules

- **Approved**: the dataset owner states terms that allow the intended reuse and the required obligations are identifiable.
- **Conditional**: reuse may be possible, but record-level licensing, share-alike, access terms, provenance, or content suitability must be resolved before publication.
- **Rejected**: the current evidence is insufficient for publication. Rejected does not mean the source is unlawful; it means SpeakSeed must not publish it through the automated pipeline.
- A repository's software license is not assumed to cover its bundled data. Audio, translations, examples and source passages are audited separately.
- An approved license does not make content `human_reviewed`. Every imported record starts in staging with review status `pending`.

## Results

| Source | Decision | License evidence | Commercial use | Available fields / suitability | Publication conditions |
|---|---|---|---|---|---|
| [CEFR-J Vocabulary and Grammar Profiles](https://github.com/openlanguageprofiles/olp-en-cefrj#terms-of-use) | **Approved** | The publisher explicitly permits research and commercial use without charge when the dataset is properly cited; copyright remains with Tono Laboratory at TUFS. | Allowed with citation | English headword, POS and CEFR-J level; no Vietnamese, IPA or audio. | Pin version 1.5, cite Yukio Tono/TUFS, retain the CEFR-J method label. Do not present CEFR-J as an official certification. |
| [Princeton WordNet 3.0](https://wordnet.princeton.edu/license-and-commercial-use) | **Approved** | Princeton permits use, copying, modification and distribution for any purpose without fee under its license. | Allowed | English senses, definitions and lexical relations; no Vietnamese, CEFR or audio. | Preserve copyright, license statements and disclaimer in copies/modifications; do not use Princeton's name in advertising; cite WordNet. |
| [Elispeak Common English Mistakes](https://github.com/elispeak/elispeak-common-english-mistakes) | **Approved for staging** | Dataset repository and its `LICENSE` state MIT, including the published JSONL content. | Allowed | Small synthetic set: learner sentence, correction, English explanation, CEFR and tags. No Vietnamese explanation. | Preserve MIT notice. Stage only; Vietnamese explanation and linguistic review are required before publication. No record may inherit `human_reviewed` automatically. |
| [Kaikki / English Wiktionary extract](https://kaikki.org/dictionary/English/) | **Conditional** | Kaikki extracts Wiktionary; [Wiktionary text is CC BY-SA 4.0 and GFDL](https://en.wiktionary.org/wiki/Wiktionary:Copyrights). | Allowed only when license obligations are met | Large English machine-readable dictionary with POS, glosses and some IPA/examples; no reliable Vietnamese or CEFR. | Pin dump date, retain page/revision attribution where available, comply with share-alike/GFDL, and review field provenance. Never assign a default CEFR. No bulk download was performed in this phase. |
| [Tatoeba text](https://tatoeba.org/en/downloads) | **Conditional** | Text exports use CC BY 2.0 FR by default; some sentences are CC0. [Tatoeba requires author/source attribution](https://en.wiki.tatoeba.org/articles/show/using-the-tatoeba-corpus). | Allowed with record-level conditions | Multilingual text and translation links; no CEFR or teaching explanation. | Preserve sentence IDs, author attribution and license notice. Verify CC0 per record. Filter correctness and naturalness before use. |
| Tatoeba audio | **Conditional / blocked by default** | The download metadata says each contributor selects an audio license; an empty license forbids reuse outside Tatoeba. | Varies by clip | Audio, speaker and attribution URL; not CEFR graded. | Import only clips whose exact license is compatible and whose attribution is retained. Text licensing does not cover audio. No audio was downloaded. |
| [Mozilla Common Voice](https://commonvoice.mozilla.org/en/datasets) | **Conditional** | Mozilla's current terms state CC0 unless a release says otherwise, while access is through Mozilla Data Collective and mirroring is restricted by platform terms. | Generally allowed for computational use, subject to exact release terms | Large speech dataset with transcripts and metadata; not a learner curriculum and not CEFR graded. | Accept the exact release terms, retain its datasheet/version, do not mirror the dataset, and verify each selected release. SpeakSeed's normal playback remains Web Speech API, so this source is not currently needed. |
| [Openjam](https://github.com/amirj4m/openjam) | **Conditional** | The repository states that the MIT license includes its data and exposes per-release attribution. | Allowed according to repository statement | WordNet-derived senses, inferred CEFR, phonetics and multilingual roadmap. The current roadmap does not list Vietnamese; translations are described as AI-generated with community review. | Pin a release, inspect `ATTRIBUTION.md`, preserve MIT notice and source flags, and independently validate translations/CEFR. AI/community claims are not evidence that a specific row was human-reviewed. |
| [Words CEFR Dataset](https://github.com/bonkey/words-cefr-dataset) | **Rejected for publication** | The repository says MIT, while the database aggregates CEFR-J, Google Books Ngram, word lists, WordNet and other inputs. A repository license alone does not establish relicensing rights for every upstream dataset. | Unverified for the compiled database | Large inferred word/POS/CEFR database; no Vietnamese meaning, IPA, examples or learner explanations. CEFR values are computed, not official labels. | Do not import until the exact revision has a field-level provenance and license compatibility review. |
| [QuALITY 1.0.1](https://nyu-mll.github.io/quality/) | **Conditional** | Project page states CC BY 4.0; records also contain a source article and article-level license field. | Potentially allowed with attribution and article-license checks | Validated long-passage multiple-choice QA; passages average about 5,000 tokens and are generally above A0–B2 learning scope. | Verify every article's `license`, author, source and jurisdictional status. Attribute both QuALITY and the article. Adapt only after CEFR/editorial review; do not copy commercial exam content. |
| [Skypedia English–Vietnamese Dictionary](https://github.com/skypediacode/english-vietnamese-dictionary) | **Conditional (existing release preserved)** | Repository/database state CC BY-SA 4.0 and list MinhQND plus several upstream resources. | Allowed if the stated upstream chain and share-alike obligations are satisfied | Vietnamese definitions and IPA, used by the existing 4,213-word merge. The source database contains 104,829 words, 158,307 definitions and 108,776 pronunciation rows in the local audited snapshot. | Preserve current IDs/data. Before expanding, complete an upstream provenance/legal review, publish attribution, mark changes and satisfy share-alike. Do not overwrite higher-quality fields. |
| [FLORES-200](https://github.com/facebookresearch/flores#licenses) | **Conditional** | Project identifies FLORES-200 as CC BY-SA 4.0 (other datasets in the same repository use different licenses). | Allowed under CC BY-SA | Parallel English–Vietnamese evaluation sentences; no CEFR. | Use only the FLORES-200 subset, preserve citation, attribution and share-alike, and perform educational/naturalness review. |
| [NTREX-128](https://github.com/MicrosoftTranslator/NTREX#license) | **Conditional** | NTREX-128 is explicitly CC BY-SA 4.0. | Allowed under CC BY-SA | Human news translation references; no CEFR and many sentences are unsuitable for beginners. | Cite NTREX and WMT19, retain source line/document, indicate adaptations and comply with share-alike. |

## Local source inventory actually inspected

No new bulk download was made during this audit. The following pre-existing local snapshots were read without modification:

| Local source | Actual records observed |
|---|---:|
| CEFR-J CSV rows processed | 7,799 |
| CEFR-J staging-valid rows under the new conservative parser | 7,627 |
| CEFR-J rejected rows | 172 (171 invalid headword-format rows, 1 duplicate stable key) |
| Skypedia dictionary words / definitions / pronunciation rows | 104,829 / 158,307 / 108,776 |
| Tatoeba/ManyThings English–Vietnamese pairs | 12,628 |
| FLORES English/Vietnamese aligned lines | 2,009 / 2,009 |
| NTREX English/Vietnamese aligned lines | 1,997 / 1,997 |

The existing deterministic vocabulary build produced **4,213** complete publishable records from 6,698 normalized CEFR candidates: A1 959, A2 972, B1 1,331 and B2 951. It rejected 2,380 candidates without a bilingual example and 105 without a compatible dictionary entry. This audit did not add, remove, publish or relabel any vocabulary record.

Counts for Kaikki, Common Voice, Openjam, Words-CEFR, Elispeak and QuALITY were not claimed because those datasets were not downloaded in this phase. Their website/repository marketing counts are not treated as locally verified record counts.

## Pipeline policy resulting from the audit

1. `approved` allows parsing into staging, not publication.
2. `conditional` requires the explicit CLI flag `--accept-conditions` even for staging.
3. `rejected`, `prohibited` or `unverified` is blocked by code.
4. The import CLI has no production/PostgreSQL publishing command.
5. `human_reviewed` can only be recorded by a separate review action with reviewer evidence; import never assigns it.
6. Audio licenses are evaluated independently from sentence-text licenses.
7. A source adapter must not invent missing Vietnamese, CEFR, IPA, examples or explanations.

## Phase 4 expansion candidates (2026-10-23)

The Phase 4 review found no additional source that can safely fill every mandatory
field for the 2,485 CEFR-J candidate headwords. No candidate was imported or
published as a result of this review.

| Candidate source | Phase 4 decision | Reason |
|---|---|---|
| [Kaikki Vietnamese Wiktionary extract](https://kaikki.org/viwiktionary/) | Conditional | Machine-readable Wiktionary data may help with individual dictionary fields, but each reused field must retain Wiktionary attribution/share-alike obligations and still needs a trustworthy learner example. |

## Phase 6 field-level provenance decision (2026-10-23)

### Existing Skypedia rows

The local `dictionary_en_vi.db` has `words`, `definitions`, `word_definitions`, and
`pronunciations`, but no field-level upstream source/version column. Skypedia's
attribution document says that definitions aggregate MinhQND, Wiktionary,
vntk/dictionary, and Hồ Ngọc Đức's project. It also says IPA was corrected and
backfilled by a pipeline that can fall back to `g2p_en`. Therefore the repository's
CC BY-SA 4.0 notice is useful dataset-level evidence, but it cannot establish which
upstream record or generation path produced a particular definition or IPA row.

Decision for the 2,220 candidate rows copied from that database:

- Vietnamese meaning: `UNVERIFIED` at field/row level; disposition `REPLACE`.
- IPA: `UNVERIFIED` at field/row level; disposition `REPLACE`.
- No row was promoted to `VERIFIED` merely from the repository-level license.
- Existing published vocabulary is preserved; this decision applies to the new
  candidate release queue.

Evidence: [Skypedia attribution](https://github.com/skypediacode/english-vietnamese-dictionary/blob/main/ATTRIBUTION.md).

### Replacement source: vi.wiktionary via Kaikki

The selected snapshot is the Vietnamese-language Wiktionary dump dated
`2026-10-02`, extracted on `2026-10-21` with Wiktextract `c1bb342` and
Wikitextprocessor `6f96ddf`. The compressed local snapshot SHA-256 is
`dcdaf93d642ae1d1c4d495b68d90eb572fac86d00281044cf804e0d98147a25e`.

Wikimedia's Terms of Use state that reusers may comply with CC BY-SA or GFDL for
dual-licensed text and that commercial reuse is allowed when the chosen license is
followed. SpeakSeed selects the CC BY-SA 4.0 path. This is `CONDITIONAL`, not
public-domain or unrestricted data. For each selected meaning SpeakSeed retains the
exact snapshot line, word/POS, page URL, dump/extractor version, license, attribution,
and a change notice. `static/data-attribution.html` makes the notice public. Any
page-specific exception remains a human-review check before publication.

Evidence:

- [Pinned Kaikki vi.wiktionary raw-data metadata](https://kaikki.org/viwiktionary/rawdata.html)
- [Wikimedia Terms of Use — licensing and reuse](https://foundation.wikimedia.org/wiki/Terms_of_Use#7._Licensing_of_Content)
- [CC BY-SA 4.0 license deed](https://creativecommons.org/licenses/by-sa/4.0/)

The license gate is `pass` only for the 100 recovered candidate rows because the
required attribution/change/share-alike mechanism is implemented. This does not
mean their linguistic content is human-reviewed.
| [CLC English–Vietnamese bilingual corpus](https://www.clc.hcmus.edu.vn/?lang=en&page_id=467) | Blocked | The public page describes and samples the corpus, but the audit did not find sufficiently explicit redistribution and commercial-use terms for publishing it in SpeakSeed. |
| [ncduy/mt-en-vi aggregate](https://huggingface.co/datasets/ncduy/mt-en-vi/blob/main/README.md) | Rejected for automatic import | The aggregate card does not establish a compatible record-level license/provenance chain for all upstream sentence pairs. |
| [ELRA Vietnamese–English comparable corpus](https://catalog.elra.info/en-us/repository/browse/ELRA-W0311/) | Not acquired | Access is licensed/paid; SpeakSeed did not purchase, download or import it. |
| [Low-resource Machine Translation corpus](https://github.com/ngovinhtn/Low-resource-Machine-Translation) | Rejected for product use | Repository terms restrict the data to research/non-commercial use and therefore do not fit a potentially public product release. |
| [EVBCorpus](https://github.com/qhungngo/EVBCorpus) | Blocked | The repository was inspected, but the audit could not establish sufficiently clear redistribution terms for automatic publication. |
