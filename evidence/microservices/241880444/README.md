# A03 微服务实操验收记录

A03 · 241880444 在本组 Linux 云主机的独立 Compose 项目中执行。表内时间统一为 **2026-11-24 UTC**，对应日本时间 11 月 25 日凌晨。教师样例和 A03 项目分别停掉自己的下游，均记录到成功、失败、恢复成功。A03 项目修复前有三条缺失依赖，修复后清零，保留原有的一条冗余依赖。

## 实际部署

| 场景 | API 入口和下游 | 运行与采集 |
| --- | --- | --- |
| 教师样例 | `POST /v1/jobs` → `worker:8080/check` | 使用包内 API 与 Worker 源码，在课程 Python 3.13.14 镜像上执行。[部署](sample/deploy/images.json) · [健康检查](sample/deploy/downstream-health.json) |
| A03 项目 | `POST /v1/jobs` → `buildchecker:8080/v1/full-check` | API 编排五个阶段。BuildChecker 是独立 HTTP 服务，执行基线、目标和修复后三次全检。[部署](project/deploy/images.json) · [健康检查](project/deploy/downstream-health.json) |
| 两套监控 | Prometheus 3.5.1 → 业务服务 `/metrics`，Grafana 13.3.0 查询 Prometheus | 采样间隔 4 秒。两套栈分别保存面板与查询结果。[项目配置和复跑入口](https://github.com/Ezio927/DevOps_BuildChecker/tree/9b7ccb060ed6b76f16270a6c51a1d9fcdf0318a2/labs/microservices) |

A03 运行版本为 [70fcf8d91b4db5d0ecdc2e660e03c81ec118105e](https://github.com/Ezio927/DevOps_BuildChecker/commit/70fcf8d91b4db5d0ecdc2e660e03c81ec118105e)。测试输入来自 241880465 提供的 A03 C/Make 项目。基线为 `e31c977a064cd593a34488e8b9ee0d1a57061fed`，目标为 `93ef2b34b5645ac3578a7b3d34792d80441b4ac6`。[原始项目 bundle](https://github.com/Ezio927/DevOps_BuildChecker/blob/70fcf8d91b4db5d0ecdc2e660e03c81ec118105e/docs/students/241880465/e13/a-project.bundle) · [实际请求](project/runs/normal/request.json)

## 停服与恢复

| 场景 | 提交或开始时间 UTC | 终态 | 错误码 | 耗时 ms | 证据 |
| --- | --- | --- | --- | ---: | --- |
| 教师样例 · 正常 | 15:53:39 | SUCCEEDED | — | 17 | [状态](sample/runs/normal/status.json) · [调用记录](sample/runs/normal/trace.log) |
| 教师样例 · 停服 | 15:53:52 | FAILED | DOWNSTREAM_UNAVAILABLE | 1004 | [状态](sample/runs/down/status.json) · [调用记录](sample/runs/down/trace.log) |
| 教师样例 · 恢复 | 15:54:07 | SUCCEEDED | — | 4 | [状态](sample/runs/recovered/status.json) · [调用记录](sample/runs/recovered/trace.log) |
| A03 项目 · 正常 | 15:53:32 | SUCCEEDED | — | 6982 | [状态](project/runs/normal/status.json) · [调用记录](project/runs/normal/trace.json) |
| A03 项目 · 停服 | 15:53:45 | FAILED | DOWNSTREAM_UNAVAILABLE | 1201 | [状态](project/runs/down/status.json) · [调用记录](project/runs/down/trace.json) |
| A03 项目 · 恢复 | 15:53:54 | SUCCEEDED | — | 3152 | [状态](project/runs/recovered/status.json) · [调用记录](project/runs/recovered/trace.json) |

**教师样例。** 停止 Worker 后，API 尝试三次，返回 `DOWNSTREAM_UNAVAILABLE`。人工启动 Worker 后首次调用成功。三阶段窗口之外还验证了慢响应，3 次读超时后进入 `TIMED_OUT`，错误码为 `DOWNSTREAM_TIMEOUT`。[慢响应记录](sample/timeout/status.json)

**A03 项目。** `15:53:41` 执行 `docker compose stop buildchecker`。故障任务先完成 DRAFT，再调用 BuildChecker 的 `baseline-full`。API 记录一次调用，工作进程返回 `DOWNSTREAM_UNAVAILABLE`。于 `15:53:50` 执行 `docker compose start buildchecker`，健康检查恢复后以新键提交相同输入。正常和恢复各有三次下游全检，故障期的调用未到达下游。每一轮以原键重复提交都返回原任务，API 日志各有一次开始、一次结束。[时间线](project/runs/timeline.json) · [故障任务](project/runs/down/result.json) · [服务日志](project/runs/services.log)

| Grafana 的实际时间窗（UTC） | 下游可达性 | 窗口结束时 API 计数 | 面板和数据 |
| --- | --- | --- | --- |
| 样例 15:53:16–15:54:16 | 1 → 0 → 1 | 成功 2、失败 1 | [面板截图](sample/monitoring/grafana.png) · [服务目标](sample/monitoring/targets.png) · [采样](sample/monitoring/window.json) |
| 项目 15:53:22–15:54:07 | 1 → 0 → 1 | 成功 2、失败 1 | [面板截图](project/monitoring/grafana.png) · [服务目标](project/monitoring/targets.png) · [采样](project/monitoring/window.json) |

两套服务都在恢复下游前，通过 Grafana 数据源读到了下游可达性为 0、失败计数为 1。Grafana 的默认查询步长会跳过短故障。截图使用与采集相同的 4 秒步长，浏览器面板返回的序列为 1 → 0 → 1。[查询配置](https://github.com/Ezio927/DevOps_BuildChecker/commit/9b7ccb060ed6b76f16270a6c51a1d9fcdf0318a2) · [项目面板读数](project/monitoring/grafana-panel-samples.json) · [样例停服读数](sample/deploy/grafana-fault.json) · [项目停服读数](project/runs/down/grafana-at-failure.json)

## 五阶段与补丁拒绝

以下使用恢复任务 `job-bb3b526c5016483aba35850892d877c1`，跨服务日志由 `trace-35e7b7d134654879925efcad0665b978` 对齐。API 与 BuildChecker 的工具链镜像 ID 为 `sha256:b56097de23a33509495ddd6014750b16247ccad67af27e68f89ed9847cd1af3b`。DRAFT 另行构建并运行候选镜像。下游检测和修复使用固定课程工具链，DRAFT 候选镜像向下游的环境交接尚未验证。

| 阶段 | 版本和环境 | 实测结果 |
| --- | --- | --- |
| DRAFT | 目标提交，API 调用 Docker，候选镜像 `sha256:abe15fdd708a815873bb3cf8142f2d6672c2c4b1f63b0d8e758f8b0a57f9c5b5` | 基线构建复现缺少 make，候选构建成功，程序输出 `1`。[DRAFT](project/runs/recovered/draft.json) |
| BuildChecker | 基线提交，独立 BuildChecker 容器 | strace 全检取得实际图和 Make 声明图，作为增量基线。[全量报告](project/runs/recovered/full-check.json) |
| EChecker | 目标提交，API 工具链，独立全检提供目标对照 | MD 为 `main.o → config.h`、`helper.o → config.h`、`helper.o → extra.h`，RD 为 `main.o → unused.h`。[增量报告](project/runs/recovered/incremental-check.json) |
| MDFixer | 目标工作副本，API 工具链 | 读取同一任务的增量报告并校验 SHA-256，补充三条声明。[修复来源](project/runs/recovered/repair.json) · [实际补丁](project/runs/recovered/candidate.patch) |
| 复验 | 目标工作副本应用补丁，独立 BuildChecker 全检 | 补丁应用、编译、程序输出、头文件增量重建、MD 清零五项通过，原有 RD 保留，无新增发现。[重检](project/runs/recovered/recheck.json) |

正常、停服、恢复三次任务分别核对 **156、46、156** 份清单产物的字节数和 SHA-256。[任务及镜像索引](summary.json)

**拒绝实验。** 对同一目标只补一条 MD。候选补丁能应用、编译并通过程序输出测试，重检仍有 MD，验证器给出 `accepted=false` 和 `rollback=true`。可写检出和源项目操作前后 HEAD、Git 状态、Makefile 哈希均相同。[部分补丁](project/rollback/partial.patch) · [前后对照](project/rollback/comparison.json) · [重检](project/rollback/validation/recheck.json)

## 复现与分工

[运行命令与环境变量](https://github.com/Ezio927/DevOps_BuildChecker/blob/9b7ccb060ed6b76f16270a6c51a1d9fcdf0318a2/labs/microservices/README.md)覆盖部署、故障和回滚。课程样例使用发放包，A03 项目使用仓库内输入与源码。241880465 提供配对项目，本记录及任务 ID 对应 241880444 的验收。Codex 在用户授权下完成代码接入、云端运行、证据核验和材料整理。
