# AGENTS.md

## 项目概述

这是一个标准的软件开发项目。

## 核心命令

### 开发

- `python -m venv venv && source venv/bin/activate` (Linux/Mac) 或 `python -m venv venv && venv\Scripts\activate` (Windows) - 创建并激活虚拟环境
- `pip install -r requirements.txt` - 安装依赖
- `python main.py` / `python -m uvicorn main:app --reload` - 启动开发服务器
- `python -m pytest` - 运行测试

### 构建

- `pip freeze > requirements.txt` - 锁定依赖版本
- `pyinstaller --onefile main.py` - 打包为可执行文件

### 测试

- `pytest` - 运行所有测试
- `pytest --cov` - 运行测试并生成覆盖率报告
- `pytest -v` - 详细输出模式运行测试

### 代码质量

- `ruff check .` / `flake8` - 运行代码检查
- `ruff check . --fix` / `black .` - 自动修复格式问题
- `mypy .` - 运行类型检查 (需要类型注解)
- `ruff format .` / `black --check .` - 检查代码格式

### Git

- `git add . && git commit -m "message"` - 提交更改
- `git push` - 推送到远程仓库
- `git status` - 查看仓库状态
- `git diff` - 查看更改内容

## 代码风格

### 命名规范

- **文件**: 小写下划线分隔 (snake_case) 或 小写下划线 (kebab-case)
- **变量/函数**: 小驼峰 (camelCase)
- **常量**: 全大写下划线分隔 (SCREAMING_SNAKE_CASE)
- **类/组件**: 大驼峰 (PascalCase)

### 组件结构

```typescript
// 1. 导入语句
// 2. 类型定义
// 3. 常量
// 4. 主组件/函数
// 5. 辅助函数
// 6. 导出
```

### 代码原则

- 单一职责原则
- 保持函数短小
- 避免深度嵌套
- 优先使用声明式代码
- 不添加不必要的注释

## 技术栈

### 前端

- HTML/ CSS / Vue
- JavaScript

### 后端

- Node.js / Python / Go
- Express / FastAPI / Gin

### 数据库

- PostgreSQL / MySQL / MongoDB

### 测试

- Jest / Vitest / Pytest
- React Testing Library

## 工作流程

### 1. 理解需求

- 阅读需求文档
- 查看相关代码
- 理解现有架构

### 2. 实现功能

- 遵循现有代码风格
- 编写测试
- 确保类型安全

### 3. 代码审查

- 运行 lint 和 typecheck
- 确保测试通过
- 检查代码覆盖率

### 4. 提交

- 编写清晰的提交信息
- 遵循 commit message 规范
- 保持提交原子性

## 常见任务

### 添加新功能

1. 创建新组件/模块
2. 编写单元测试
3. 更新类型定义
4. 运行完整测试套件

### 修复 Bug

1. 编写失败的测试
2. 修复代码使测试通过
3. 运行完整测试套件

### 重构

1. 确保有测试覆盖
2. 小步前进
3. 每步都运行测试

## 注意事项

- 不要修改不相关的代码
- 保持 PR 小而专注
- 编写有意义的测试
- 遵循语义化版本
- 不要提交敏感信息
