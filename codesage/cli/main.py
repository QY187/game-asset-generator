"""CLI命令入口。"""

from __future__ import annotations

import sys

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from codesage.core.ai_analyzer import AIAnalyzer
from codesage.core.pr_parser import parse_pr_url
from codesage.core.pr_service import PRService
from codesage.models.config import Config
from codesage.providers.ai_provider import AIProviderFactory
from codesage.utils.config import load_config

app = typer.Typer(help="CodeSage - AI驱动的代码审查工具")
console = Console()


def print_banner():
    """打印启动横幅。"""
    banner = """
   ______          __    _____                      
  / ____/___  ____/ /__ / ___/___  ____ ____   ____ 
 / /   / __ \\/ __  / _ \\\\__ \\/ _ \\/ __ `/ _ \\ / __ \\
/ /___/ /_/ / /_/ /  __/__/ /  __/ /_/ / (_) / /_/ /
\\____/\\____/\\__,_/\\___/____/\\___/\\__, /\\___/\\____/ 
                                /____/             
"""
    console.print(f"[bold blue]{banner}[/bold blue]")


@app.command()
def analyze(
    pr_url: str = typer.Argument(..., help="PR URL (GitHub/Gitee)"),
    provider: str = typer.Option("openai", "--provider", help="AI厂商"),
    model: str | None = typer.Option(None, "--model", help="使用的AI模型（留空则使用该厂商默认模型）"),
    comment: bool = typer.Option(False, "--comment", help="是否将分析结果发布到PR评论"),
    output: str = typer.Option(None, "--output", help="输出分析结果到文件")
):
    """分析指定的PR代码变更。"""
    print_banner()
    config = load_config()
    provider_name = Config.normalize_provider(provider or config.ai_provider)
    selected_model = model or Config.default_model_for(provider_name)
    if selected_model not in Config.model_options_for(provider_name):
        console.print(
            f"[yellow]⚠️ 模型 {selected_model} 不属于 {provider_name}，已自动切换为默认模型 {Config.default_model_for(provider_name)}[/yellow]"
        )
        selected_model = Config.default_model_for(provider_name)
    
    # 解析PR URL
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        
        task1 = progress.add_task("[cyan]解析PR URL...", total=None)
        try:
            pr_ref = parse_pr_url(pr_url)
            console.print(f"✅ 识别PR: [bold]{pr_ref.owner}/{pr_ref.repo}#{pr_ref.pr_number}[/bold] (平台: {pr_ref.platform})")
            progress.update(task1, completed=True)
        except ValueError as e:
            console.print(f"[red]❌ 错误: {e}[/red]")
            raise typer.Exit(1)
        
        # 获取PR信息
        task2 = progress.add_task("[cyan]获取PR信息...", total=None)
        try:
            pr_service = PRService(github_token=config.github_token)
            pr = pr_service.get_pr(pr_ref)
            console.print(f"✅ 标题: [bold]{pr.metadata.title}[/bold]")
            console.print(f"✅ 作者: {pr.metadata.author}")
            console.print(f"✅ 文件变更: {len(pr.files)} 个")
            console.print(f"✅ Commit: {len(pr.commits)} 个")
            progress.update(task2, completed=True)
        except Exception as e:
            console.print(f"[red]❌ 获取PR信息失败: {e}[/red]")
            raise typer.Exit(1)
        
        # AI分析
        task3 = progress.add_task("[cyan]AI分析中...", total=None)
        try:
            openai_provider = AIProviderFactory.create(
                provider=provider_name,
                api_key=config.get_api_key(provider_name),
                base_url=config.get_base_url(provider_name),
            )
            analyzer = AIAnalyzer(openai_provider, provider=provider_name)
            result = analyzer.analyze_pr(pr, model=selected_model)
            progress.update(task3, completed=True)
        except Exception as e:
            console.print(f"[red]❌ AI分析失败: {e}[/red]")
            raise typer.Exit(1)
    
    # 输出分析结果
    console.print("\n" + "=" * 60)
    console.print(Panel.fit("[bold cyan]📋 分析结果[/bold cyan]", padding=1))
    console.print("=" * 60)
    
    console.print(result.summary)
    
    # 输出到文件
    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(result.summary)
        console.print(f"\n✅ 分析结果已保存到: [bold]{output}[/bold]")
    
    # 发布评论
    if comment:
        console.print("\n[cyan]正在发布评论到PR...[/cyan]")
        try:
            pr_service.post_comment(pr_ref, result.summary)
            console.print("✅ 评论发布成功!")
        except Exception as e:
            console.print(f"[red]❌ 发布评论失败: {e}[/red]")
    
    console.print("\n[bold green]✨ 分析完成![/bold green]")


@app.command()
def version():
    """显示版本信息。"""
    print_banner()
    console.print("[bold]CodeSage v0.1.0[/bold]")
    console.print("AI驱动的代码审查工具")


if __name__ == "__main__":
    app()
