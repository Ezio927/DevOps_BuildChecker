# 在 A03 项目上复跑微服务验收

E12 API 接收课程的 `POST /v1/jobs` 请求。基线全检、目标全量对照和修复后重检通过 Compose 服务名调用 BuildChecker。DRAFT、EChecker、MDFixer 在 API 的任务进程中执行。API 和 BuildChecker 共用该次实验的产物目录，各自暴露 `/health` 和 `/metrics`。Prometheus 每 4 秒采样，Grafana 面板展示服务是否可达、任务终态与耗时。

## 准备

在个人 Linux 检出中，从仓库根目录执行。需要 Docker、Compose、Python 3，以及课程包中 `scripts/project.py` 和同目录的 `lab.py`。将环境变量 `SAMPLE_DIR` 设为解压后的样例目录绝对路径。使用课程镜像源时，`PROMETHEUS_IMAGE`、`GRAFANA_IMAGE` 可设为可访问的同版本镜像引用。

```bash
read -rp '学号 ' sid
git config --local user.name "$sid"
python3 run_e11e12.py build
export PROJECT_IMAGE="course-e11e12:$sid"
export LAB_UID="$(id -u)" LAB_GID="$(id -g)" DOCKER_GID="$(stat -c %g /var/run/docker.sock)"
export GRAFANA_ADMIN_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
mkdir -p work data/paired/A-project
export MICRO_WORK="$(mktemp -d "$PWD/work/microservices.XXXXXX")"
export COMPOSE_PROJECT_NAME="a03-micro-$sid"
git clone docs/students/241880465/e13/a-project.bundle data/paired/A-project/repo
git -C data/paired/A-project/repo checkout --detach 93ef2b34b5645ac3578a7b3d34792d80441b4ac6
cp labs/microservices/candidate.Dockerfile data/paired/A-project/
cd labs/microservices
docker compose config --quiet && docker compose up -d --wait
docker compose ps
```

默认 API、Prometheus、Grafana 分别绑定本机 `18080`、`19090`、`13000`。多人共用主机时，为自己的 Compose 项目设置空闲的 `LAB_API_PORT`、`LAB_PROM_PORT`、`LAB_GRAFANA_PORT` 后再启动。Grafana 用户为 `admin`，面板名为「A03 · E12 任务与全量检测」。跨机查看时使用 SSH 本地端口转发。

## 运行正常、停服、恢复和补丁拒绝

```bash
out="$MICRO_WORK/acceptance"
python3 accept.py --sample-dir "$SAMPLE_DIR" --out "$out" \
  --api-port "${LAB_API_PORT:-18080}" --prom-port "${LAB_PROM_PORT:-19090}" --grafana-port "${LAB_GRAFANA_PORT:-13000}"
jid=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["job_id"])' "$out/recovered/check.json")
docker compose exec -T api python3 labs/microservices/rollback.py \
  /course/data/paired/A-project/repo "/course/work/api-jobs/$jid/evidence/incremental-check.json" /course/work/rollback
```

`accept.py` 会在当前 Compose 项目停止并恢复 `buildchecker`。同一输入的三次任务分别使用新幂等键。每次另用原键重复提交，并通过日志验证只执行了一次。正常与恢复轮次均运行教师的 E12 客户端，核对五阶段、提交 SHA、补丁和报告哈希。故障轮次核对已完成 DRAFT、全检不可达的错误码和 Prometheus 实际采到的失败计数。

补丁拒绝实验从成功任务的 MD 报告中选一条生成可应用的部分补丁。验收要求它能编译、重检仍有 MD、验证器拒绝，并且可写检出的 HEAD、Git 状态和 Makefile 字节均与操作前相同。结果在 `$MICRO_WORK/rollback/comparison.json`。

## 导出同一窗口的监控

```bash
read start end < <(python3 - "$out/timeline.json" <<'PY'
import json, sys
from datetime import datetime
t = json.load(open(sys.argv[1]))
print(int(datetime.fromisoformat(t['start']).timestamp()) - 10,
      int(datetime.fromisoformat(t['end']).timestamp()))
PY
)
python3 observe.py --grafana "http://127.0.0.1:${LAB_GRAFANA_PORT:-13000}" \
  --uid a03-e12 --start "$start" --end "$end" --out "$out/monitoring"
docker compose down
```

导出内容包括 Grafana 实际加载的面板与每条面板查询返回的时间序列。查看 `runs` 对应的任务时，用 `job_id` 找任务，用 `trace_id` 关联 API 与 BuildChecker 事件。服务重启后该进程的完成计数从零开始，API 在这次下游停机期间持续记录任务终态。
