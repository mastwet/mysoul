class ExecutionDisabled(PermissionError):
    pass


class ExecutionTool:
    available = False

    async def run(self, code: str):
        raise ExecutionDisabled("No verified isolation backend is installed; execution is disabled")
