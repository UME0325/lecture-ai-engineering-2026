| 質問 | 方式 | 時間(秒) | 入力/出力 tokens | 応答回数 | 推定費用 | ツール呼び出し | 回答中の引用 | 備考 |
|---|---|---|---|---|---|---|---|---|
| q1_lora | full_context | 2.01 | 117,025/264 | 1 | $0.004811 | なし | なし |  |
| q1_lora | graph | 3.12 | 5,771/185 | 2 | $0.001646 | search_graph×1 | 2回p.51, 2回p.52 |  |
| q1_lora | guided | 4.08 | 7,826/268 | 3 | $0.003018 | search_graph_guided×1, read_pages×1 | 2回p.51, 2回p.52 |  |
| q1_lora | guided_v2_r1 | 2.70 | 4,333/201 | 2 | $0.001802 | search_graph_guided×1 | 2回p.51, 2回p.52 |  |
| q1_lora | guided_v2_r2 | 3.19 | 4,330/171 | 2 | $0.001726 | search_graph_guided×1 | 2回p.51, 2回p.52 |  |
| q1_lora | guided_v2_r3 | 3.23 | 4,330/256 | 2 | $0.001939 | search_graph_guided×1 | 2回p.51, 2回p.52 |  |
| q1_lora | tree | 5.54 | 9,214/324 | 5 | $0.003574 | browse_tree×4 | 2回p.52 |  |
| q1_lora | vector | 3.09 | 3,037/194 | 2 | $0.001396 | search_materials×1 | 2回p.51, 2回p.52 |  |
| q2_memory | graph | 3.38 | 5,301/333 | 2 | $0.002423 | search_graph×1 | 3回p.39, 3回p.40, 3回p.65 |  |
| q2_memory | guided | 5.42 | 6,296/621 | 3 | $0.003441 | search_graph_guided×1, read_pages×1 | 3回p.38, 3回p.39, 3回p.40, 3回p.65 |  |
| q2_memory | guided_r2 | 4.90 | 6,296/620 | 3 | $0.003439 | search_graph_guided×1, read_pages×1 | 3回p.13, 3回p.38, 3回p.39, 3回p.40, 3回p.65 |  |
| q2_memory | guided_r3 | 5.09 | 6,296/531 | 3 | $0.003216 | search_graph_guided×1, read_pages×1 | 3回p.13, 3回p.38, 3回p.39, 3回p.40 |  |
| q2_memory | guided_v2_r1 | 3.67 | 3,663/480 | 2 | $0.002299 | search_graph_guided×1 | 3回p.13, 3回p.38, 3回p.39, 3回p.40 |  |
| q2_memory | guided_v2_r2 | 3.58 | 3,641/440 | 2 | $0.002192 | search_graph_guided×1 | 3回p.13, 3回p.38, 3回p.39, 3回p.40, 3回p.65 |  |
| q2_memory | guided_v2_r3 | 3.46 | 3,641/414 | 2 | $0.002127 | search_graph_guided×1 | 3回p.13, 3回p.38, 3回p.39, 3回p.40 |  |
| q2_memory | tree | 7.97 | 11,045/677 | 7 | $0.005006 | browse_tree×6 | 3回p.39, 3回p.40 |  |
| q2_memory | vector | 3.61 | 2,500/458 | 2 | $0.001895 | search_materials×1 | 3回p.13, 3回p.39, 3回p.40, 3回p.65 |  |
| q2_memory | vector_r2 | 3.53 | 2,500/489 | 2 | $0.001972 | search_materials×1 | 3回p.13, 3回p.39, 3回p.40, 3回p.65 |  |
| q2_memory | vector_r3 | 3.25 | 2,495/446 | 2 | $0.001864 | search_materials×1 | 3回p.13, 3回p.38, 3回p.39, 3回p.40 |  |
| q3_cross | graph | 6.88 | 13,560/460 | 3 | $0.004120 | search_graph×2 | 2回p.46, 2回p.47, 2回p.53, 3回p.13, 3回p.38 |  |
| q3_cross | guided | 6.54 | 13,093/524 | 4 | $0.004693 | search_graph_guided×2, read_pages×1 | 2回p.46, 2回p.53, 3回p.13, 3回p.38, 3回p.39 |  |
| q3_cross | guided_v2_r1 | 4.98 | 9,562/448 | 3 | $0.003989 | search_graph_guided×2 | 2回p.46, 2回p.53, 3回p.13, 3回p.38, 3回p.39 |  |
| q3_cross | guided_v2_r2 | 5.60 | 9,562/538 | 3 | $0.003667 | search_graph_guided×2 | 2回p.46, 2回p.53, 3回p.13, 3回p.38 |  |
| q3_cross | guided_v2_r3 | 5.16 | 9,562/454 | 3 | $0.003457 | search_graph_guided×2 | 2回p.46, 2回p.53, 3回p.13, 3回p.38, 3回p.39, 3回p.65 |  |
| q3_cross | vector | 5.22 | 6,391/561 | 3 | $0.003320 | search_materials×2 | 2回p.46, 2回p.53, 3回p.13, 3回p.38, 3回p.39 |  |
| q4_absent | graph | 3.25 | 5,335/154 | 2 | $0.001438 | search_graph×1 | 2回p.13 |  |
| q4_absent | guided | 3.56 | 3,509/218 | 2 | $0.001598 | search_graph_guided×1 | 2回p.13 |  |
| q4_absent | guided_v2_r1 | 3.01 | 4,158/228 | 2 | $0.001817 | search_graph_guided×1 | 2回p.13, 2回p.14 |  |
| q4_absent | guided_v2_r2 | 2.69 | 4,158/181 | 2 | $0.001700 | search_graph_guided×1 | 2回p.13 |  |
| q4_absent | guided_v2_r3 | 3.38 | 4,158/183 | 2 | $0.001705 | search_graph_guided×1 | 2回p.13 |  |
| q4_absent | vector | 3.33 | 3,205/145 | 2 | $0.001324 | search_materials×1 | 2回p.13 |  |
