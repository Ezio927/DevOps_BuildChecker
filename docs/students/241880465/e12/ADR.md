# E12 决策记录

选择复用 B 仓库已合入的 external incremental report 接口，A 在独立源码目录生成报告，B 校验原始字节 SHA256 后消费。跨仓库任务保留各自身份，通过 provenance 追踪来源；每轮 B 编排的五阶段统一使用本轮身份。

个人验证进一步检查完整 payload，并对目标实际图、声明图与发现进行全量对照，防止 findings 相同但图数据被改变。验收脚本直接用于实际运行产物，测试通过现有 A-only 发现入口执行。

项目选择沿用组内维护的 fixtures/draft 适配项目及完整 bundle 历史，经用户同意后恢复并重新执行。保留原来源和 external_real_project=false 标记。API 使用本人专用回环端口及 SSH 转发，实验结束后停止测试容器。
