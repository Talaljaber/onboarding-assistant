# kb_anchors.csv provenance

- Written on 2026-11-11 from `data/official/knowledge_base.csv` only (rows K01-K18).
- The author never saw any evaluation set (eval_dev, eval_heldout), the sample FAQ, or the jury test-case file.
- 4 anchors per row (72 total): 2 Modern Standard Arabic, 2 Jordanian/Levantine dialect; each answerable by its row alone. `source` = `ours`.
- Use: only for the offline out-of-scope margin (row side). Never used for ranking.
- Rows that are live-edited or added later have no anchors and fall back to the row text.
- sha256 of `kb_anchors.csv`: `82e1897c7024eededac7eae3889ee8e68ba0be6694f137363393f18b181c3d2c`
