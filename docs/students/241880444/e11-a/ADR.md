# ADR：A-only 隔离集成与完整图验收

仅执行 E11-A 时复用现有 A 工具链，不需要 Docker-in-Docker、Docker socket、bridge 网络或 API。
保留课程共享模块供后续集成，但 A 工作流不触发 B/E12 分支。
目标验收同时比较提交、actual、declared、findings，防止仅错误集合一致掩盖图错误。
使用 C0—C3 的真实控制样例提交，手工边集独立判定；保存所有封装与内容摘要。
代价是范围仍受双 C 源文件和显式 Make 规则限制；真实外部项目需要额外适配，后续再验收。
