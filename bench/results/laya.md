# LUAR evaluation (2026-10-02)

| Dataset | Engine | Question | Type | Accuracy | Extra | ECE | Acc. conf≥0.7 (share) | Acc. conf<0.7 | s/row |
|---|---|---|---|---:|---|---:|---|---:|---:|
| b2w | laya (multilingual, chosen automatically) | recomenda | noul | 70% |  | 0.184 | 72% (82%) | 62% | 1.28 |
| b2w | laya (multilingual, chosen automatically) | sentimento | choice | 68% |  | 0.177 | 75% (83%) | 36% | 1.28 |
| b2w | laya (multilingual, chosen automatically) | estrelas | score | 26% | ±1: 60%, MAE 1.383 | 0.123 | 15% (4%) | 26% | 1.28 |
| ag_news | laya (english, chosen automatically) | topic | choice | 93% |  | 0.085 | 98% (84%) | 66% | 1.0 |
