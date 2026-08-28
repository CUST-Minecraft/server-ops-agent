import typer

app = typer.Typer(help="ServerOpsAgent -- 智能服务器运维 Agent")

@app.command()
def run():
    """启动自治闭环（监控+检测+调查+修复）"""
    from app.runtime.runner import run as runner_run
    runner_run()

@app.command()
def incidents(n: int = typer.Option(10, help="显示条数")):
    """显示最近工单"""
    ...

if __name__ == "__main__":
    app()