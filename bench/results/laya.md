# LUAR evaluation (2026-11-27)

| Dataset | Engine | Question | Type | Accuracy | Extra | ECE | Acc. conf≥0.7 (share) | Acc. conf<0.7 | s/row |
|---|---|---|---|---:|---|---:|---|---:|---:|
| b2w | laya (multilingual, chosen automatically) | recomenda | noul | 70% |  | 0.184 | 72% (82%) | 62% | 1.09 |
| b2w | laya (multilingual, chosen automatically) | sentimento | choice | 68% |  | 0.177 | 75% (83%) | 36% | 1.09 |
| b2w | laya (multilingual, chosen automatically) | estrelas | score | 33% | ±1: 68%, MAE 1.167 | 0.324 | 44% (44%) | 24% | 1.09 |
| ag_news | laya (english, chosen automatically) | topic | choice | 93% |  | 0.085 | 98% (84%) | 66% | 0.63 |
