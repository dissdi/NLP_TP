# T1 5-cat - 04_index BM25 Report

## Tokenizer
- kiwipiepy 0.23 (matches Phase C builder)
- kept POS: NNB, NNG, NNP, NP, NR, SH, SL, SN, VA, VCN, VCP, VV, VX, XR

## Tracks
| track | chunks | tokens(total) | avg/min/max | tok sec | build sec |
|---|---:|---:|---|---:|---:|
| `general` | 1151 | 210414 | 182.8 / 9 / 573 | 12.1 | 0.04 |

Metadata lookup: 1151 in-scope rows -> `data/phase_c_5cat/04_index/meta/chunks.jsonl`

## Policy notes
- 5-cat in-scope only; almi_cell/almi_dept moved to corpus_out_of_scope/
- single-track general (no almi sparse track)
- queries at retrieval time must be tokenized with the SAME function
