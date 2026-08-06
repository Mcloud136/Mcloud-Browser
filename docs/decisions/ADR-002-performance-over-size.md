# ADR-002：性能优先原则——体积不作约束，Windows 必须全量 -O3

- **状态**：已采纳
- **日期**：2026-08-05
- **决策人**：项目方
- **依据条款**：`docs/architecture/performance-build-technical-spec.md` 1.7、2.1

## 背景

Chromium 上游出于体积与可维护性考虑默认使用 -O2，并对全量 -O3 持谨慎态度（`src/build/config/compiler/BUILD.gn` 第 3079-3091 行上游注释：Android 上全量 -O3 对 Speedometer 收益甚微但增大体积）。此前规范中存在"以 ICF/BOLT 抵消 -O3 体积膨胀"、"热点目标选择性 -O3"等以体积为约束的表述。

## 决策

1. **性能为项目第一目标**：二进制体积不作为约束指标，任何优化决策不得以牺牲运行时性能换取体积。
2. **Windows 官方构建（`is_official_build = true`）必须保持全量 -O3**，禁止任何以体积为由降级优化等级的变更。
3. **二进制体积仅作观测指标记录（K7）**，不设上限、不作为发布阻断条件。
4. 规范 10.3"热点目标选择性 -O3"调整为默认不启用，仅当基准数据证明全量 -O3 因 i-cache 压力出现性能回归时才考虑。

## -O3 生效链路（升级时须核对）

- `src/build/config/compiler/BUILD.gn` 的 `optimize` config（约第 3092-3100 行）：`is_win` 显式叠加 `/O2` + `/clang:-O3` + `-Xclang -O3`；
- 同文件 `no_chromium_code` config（约第 2515-2550 行）：第三方代码追加 `-Xclang -O3`；
- `-mllvm -aggressive-ext-opt` 与 `-mllvm -enable-gvn-hoist` 调优开关（约第 2888-2927 行）。

## 后果与约束

- 每次内核升级 rebase 后，须逐一核对上述链路未被上游回退（规范 2.1 条款）。
- 涉及体积/性能取舍的方案评审，一律按性能优先裁决。
