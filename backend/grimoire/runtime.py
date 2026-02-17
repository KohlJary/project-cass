"""
Grimoire Runtime (Spellcaster)

Interprets and executes parsed spells.
"""

import asyncio
import logging
from typing import Any, Optional

from .ast import (
    # Base
    Spell,
    Expression,
    Statement,
    # Statements
    IfStatement,
    ForEachStatement,
    ForStatement,
    WhileStatement,
    LabelStatement,
    GotoStatement,
    GosubStatement,
    ReturnStatement,
    ExitStatement,
    WaitStatement,
    ContinueStatement,
    BreakStatement,
    LetStatement,
    ParallelBlock,
    # Actions
    CareAction,
    TaskAction,
    EmitAction,
    LogAction,
    DeltaAction,
    ResetAction,
    CastStatement,
    # Agentic
    AskStatement,
    ChooseStatement,
    RateStatement,
    GenerateStatement,
    ReflectStatement,
    # Expressions
    BinaryOp,
    UnaryOp,
    Variable,
    Literal,
    PropertyAccess,
    FunctionCall,
    Interpolation,
)
from .context import SpellContext, ExitStatus, RuntimeServices

logger = logging.getLogger(__name__)


class SpellError(Exception):
    """Error during spell execution."""
    def __init__(self, message: str, line: int = 0, column: int = 0):
        self.message = message
        self.line = line
        self.column = column
        super().__init__(f"Line {line}: {message}" if line else message)


class Spellcaster:
    """
    Executes parsed spells.

    Usage:
        caster = Spellcaster(services)
        result = await caster.cast(spell, event_data={})
    """

    def __init__(self, services: RuntimeServices):
        self.services = services

    async def cast(
        self,
        spell: Spell,
        event_data: Optional[dict[str, Any]] = None,
        shadow_mode: bool = True,
        trace: bool = False,
    ) -> dict[str, Any]:
        """
        Execute a spell.

        Args:
            spell: The parsed spell to execute
            event_data: Data from triggering event (if any)
            shadow_mode: If True, don't execute external actions
            trace: If True, record execution trace

        Returns:
            Dict with execution result
        """
        ctx = SpellContext(
            spell=spell,
            event_data=event_data or {},
            shadow_mode=shadow_mode,
            trace_enabled=trace,
        )

        # Set up EVENT_DATA variable
        ctx.set_variable("EVENT_DATA", ctx.event_data)

        logger.info(f"Casting spell: {spell.metadata.name}")
        ctx.add_trace(f"Begin spell: {spell.metadata.name}")

        try:
            await self._execute_body(ctx, spell.body)
        except SpellError as e:
            logger.error(f"Spell error in {spell.metadata.name}: {e}")
            ctx.exit(ExitStatus.FAILURE, str(e))
        except Exception as e:
            logger.exception(f"Unexpected error in spell {spell.metadata.name}")
            ctx.exit(ExitStatus.FAILURE, f"Unexpected error: {e}")

        # If we didn't explicitly exit, mark as success
        if ctx.is_running():
            ctx.exit(ExitStatus.SUCCESS)

        ctx.add_trace(f"End spell: {ctx.exit_status.name}")

        return {
            "status": ctx.exit_status.name.lower(),
            "reason": ctx.exit_reason,
            "variables": dict(ctx.variables),
            "trace": ctx.trace if trace else None,
        }

    async def _execute_body(self, ctx: SpellContext, body: list[Statement]) -> None:
        """Execute a list of statements."""
        index = 0
        while index < len(body) and ctx.is_running():
            stmt = body[index]
            ctx.current_index = index
            ctx.add_trace(f"Execute: {type(stmt).__name__} at line {stmt.line}")

            # Check for loop control
            loop = ctx.current_loop()
            if loop and (loop.should_break or loop.should_continue):
                break

            # Execute statement
            result = await self._execute_statement(ctx, stmt)

            # Handle GOTO/GOSUB - result is new index
            if isinstance(result, int):
                index = result
            else:
                index += 1

    async def _execute_statement(self, ctx: SpellContext, stmt: Statement) -> Optional[int]:
        """
        Execute a single statement.

        Returns new index for GOTO/GOSUB, or None for normal flow.
        """
        # Skip labels - they're just markers
        if isinstance(stmt, LabelStatement):
            return None

        # Control flow
        if isinstance(stmt, IfStatement):
            await self._exec_if(ctx, stmt)
        elif isinstance(stmt, ForEachStatement):
            await self._exec_for_each(ctx, stmt)
        elif isinstance(stmt, ForStatement):
            await self._exec_for(ctx, stmt)
        elif isinstance(stmt, WhileStatement):
            await self._exec_while(ctx, stmt)
        elif isinstance(stmt, GotoStatement):
            return self._exec_goto(ctx, stmt)
        elif isinstance(stmt, GosubStatement):
            return self._exec_gosub(ctx, stmt)
        elif isinstance(stmt, ReturnStatement):
            return self._exec_return(ctx)
        elif isinstance(stmt, ExitStatement):
            self._exec_exit(ctx, stmt)
        elif isinstance(stmt, WaitStatement):
            await self._exec_wait(ctx, stmt)
        elif isinstance(stmt, ContinueStatement):
            ctx.signal_continue()
        elif isinstance(stmt, BreakStatement):
            ctx.signal_break()
        elif isinstance(stmt, ParallelBlock):
            await self._exec_parallel(ctx, stmt)

        # Variable assignment
        elif isinstance(stmt, LetStatement):
            await self._exec_let(ctx, stmt)

        # Actions
        elif isinstance(stmt, CareAction):
            await self._exec_care(ctx, stmt)
        elif isinstance(stmt, TaskAction):
            await self._exec_task(ctx, stmt)
        elif isinstance(stmt, EmitAction):
            await self._exec_emit(ctx, stmt)
        elif isinstance(stmt, LogAction):
            await self._exec_log(ctx, stmt)
        elif isinstance(stmt, DeltaAction):
            await self._exec_delta(ctx, stmt)
        elif isinstance(stmt, ResetAction):
            await self._exec_reset(ctx, stmt)
        elif isinstance(stmt, CastStatement):
            await self._exec_cast(ctx, stmt)

        # Agentic
        elif isinstance(stmt, AskStatement):
            await self._exec_ask(ctx, stmt)
        elif isinstance(stmt, ChooseStatement):
            await self._exec_choose(ctx, stmt)
        elif isinstance(stmt, RateStatement):
            await self._exec_rate(ctx, stmt)
        elif isinstance(stmt, GenerateStatement):
            await self._exec_generate(ctx, stmt)
        elif isinstance(stmt, ReflectStatement):
            await self._exec_reflect(ctx, stmt)

        else:
            raise SpellError(f"Unknown statement type: {type(stmt).__name__}", stmt.line, stmt.column)

        return None

    # =========================================================================
    # CONTROL FLOW
    # =========================================================================

    async def _exec_if(self, ctx: SpellContext, stmt: IfStatement) -> None:
        """Execute IF statement."""
        condition = await self._eval_expr(ctx, stmt.condition)

        if condition:
            await self._execute_body(ctx, stmt.then_body)
        else:
            # Check else-if clauses
            executed = False
            for elif_cond, elif_body in stmt.else_if_clauses:
                if await self._eval_expr(ctx, elif_cond):
                    await self._execute_body(ctx, elif_body)
                    executed = True
                    break

            if not executed and stmt.else_body:
                await self._execute_body(ctx, stmt.else_body)

    async def _exec_for_each(self, ctx: SpellContext, stmt: ForEachStatement) -> None:
        """Execute FOR EACH statement."""
        collection = await self._eval_expr(ctx, stmt.collection)

        # Handle special collections
        if isinstance(collection, str):
            if collection == "NEEDS":
                collection = list(self.services.thymos.get_all_needs().values())
            elif collection == "AFFECTS":
                affects = self.services.thymos.get_all_affects()
                collection = [{"name": k, "value": v} for k, v in affects.items()]

        if not hasattr(collection, '__iter__'):
            raise SpellError(f"Cannot iterate over {type(collection)}", stmt.line)

        loop_ctx = ctx.push_loop("for_each")

        for item in collection:
            if not ctx.is_running() or loop_ctx.should_break:
                break

            loop_ctx.should_continue = False

            # Apply filter if present
            if stmt.filter_condition:
                ctx.set_variable(stmt.item_var, item)
                if not await self._eval_expr(ctx, stmt.filter_condition):
                    continue

            ctx.set_variable(stmt.item_var, item)
            await self._execute_body(ctx, stmt.body)

        ctx.pop_loop()

    async def _exec_for(self, ctx: SpellContext, stmt: ForStatement) -> None:
        """Execute FOR ... TO statement."""
        start = int(await self._eval_expr(ctx, stmt.start))
        end = int(await self._eval_expr(ctx, stmt.end))
        step = int(await self._eval_expr(ctx, stmt.step)) if stmt.step else 1

        loop_ctx = ctx.push_loop("for")

        i = start
        while (step > 0 and i <= end) or (step < 0 and i >= end):
            if not ctx.is_running() or loop_ctx.should_break:
                break

            loop_ctx.should_continue = False
            ctx.set_variable(stmt.var_name, i)
            await self._execute_body(ctx, stmt.body)
            i += step

        ctx.pop_loop()

    async def _exec_while(self, ctx: SpellContext, stmt: WhileStatement) -> None:
        """Execute WHILE statement."""
        loop_ctx = ctx.push_loop("while")

        while ctx.is_running() and not loop_ctx.should_break:
            loop_ctx.should_continue = False

            condition = await self._eval_expr(ctx, stmt.condition)
            if not condition:
                break

            await self._execute_body(ctx, stmt.body)

        ctx.pop_loop()

    def _exec_goto(self, ctx: SpellContext, stmt: GotoStatement) -> int:
        """Execute GOTO statement. Returns new statement index."""
        label = stmt.target_label
        if label not in ctx.spell.labels:
            raise SpellError(f"Unknown label: {label}", stmt.line)
        return ctx.spell.labels[label]

    def _exec_gosub(self, ctx: SpellContext, stmt: GosubStatement) -> int:
        """Execute GOSUB statement. Returns new statement index."""
        label = stmt.target_label
        if label not in ctx.spell.labels:
            raise SpellError(f"Unknown label: {label}", stmt.line)

        # Push return address (current position + 1)
        ctx.push_call(ctx.current_index + 1, label)
        return ctx.spell.labels[label]

    def _exec_return(self, ctx: SpellContext) -> int:
        """Execute RETURN statement. Returns statement index to return to."""
        frame = ctx.pop_call()
        if frame is None:
            raise SpellError("RETURN without GOSUB", 0)
        return frame.return_index

    def _exec_exit(self, ctx: SpellContext, stmt: ExitStatement) -> None:
        """Execute EXIT statement."""
        status_map = {
            "SUCCESS": ExitStatus.SUCCESS,
            "FAILURE": ExitStatus.FAILURE,
            "SKIPPED": ExitStatus.SKIPPED,
        }
        ctx.exit(status_map.get(stmt.status, ExitStatus.SUCCESS), stmt.reason)

    async def _exec_wait(self, ctx: SpellContext, stmt: WaitStatement) -> None:
        """Execute WAIT statement."""
        seconds = await self._eval_expr(ctx, stmt.seconds)
        ctx.add_trace(f"Waiting {seconds} seconds")
        await asyncio.sleep(float(seconds))

    async def _exec_parallel(self, ctx: SpellContext, stmt: ParallelBlock) -> None:
        """Execute PARALLEL block."""
        # Create tasks for each branch
        async def run_branch(body: list[Statement]) -> None:
            await self._execute_body(ctx, body)

        tasks = [asyncio.create_task(run_branch(branch)) for branch in stmt.branches]

        if stmt.wait_mode == "ALL":
            await asyncio.gather(*tasks)
        else:  # FIRST
            _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()

    # =========================================================================
    # VARIABLE ASSIGNMENT
    # =========================================================================

    async def _exec_let(self, ctx: SpellContext, stmt: LetStatement) -> None:
        """Execute LET statement."""
        value = await self._eval_expr(ctx, stmt.value)
        ctx.set_variable(stmt.var_name, value)
        ctx.add_trace(f"Set ${stmt.var_name} = {value}")

    # =========================================================================
    # ACTIONS
    # =========================================================================

    async def _exec_care(self, ctx: SpellContext, stmt: CareAction) -> None:
        """Execute CARE action."""
        if stmt.action_key:
            action_key = stmt.action_key
        elif stmt.for_need:
            need_name = await self._eval_expr(ctx, stmt.for_need)
            # If it's a need object, get the name
            if hasattr(need_name, 'name'):
                need_name = need_name.name
            action_key = self.services.thymos.get_care_action_for_need(need_name)
            if not action_key:
                ctx.add_trace(f"No care action for need: {need_name}")
                return
        else:
            raise SpellError("CARE requires action key or FOR need", stmt.line)

        ctx.add_trace(f"Care action: {action_key}")

        if not ctx.shadow_mode:
            await self.services.thymos.execute_care_action(action_key)
        else:
            logger.debug(f"Shadow mode: would execute care action {action_key}")

    async def _exec_task(self, ctx: SpellContext, stmt: TaskAction) -> None:
        """Execute TASK action."""
        params = {}
        for key, expr in stmt.parameters.items():
            params[key] = await self._eval_expr(ctx, expr)

        ctx.add_trace(f"Task: {stmt.action} params={params} await={stmt.await_completion}")

        if not ctx.shadow_mode:
            result = await self.services.scheduler.execute_task(
                stmt.action, params, stmt.await_completion
            )
            ctx.set_variable("TASK_RESULT", result)
        else:
            logger.debug(f"Shadow mode: would execute task {stmt.action}")
            ctx.set_variable("TASK_RESULT", {"shadow": True})

    async def _exec_emit(self, ctx: SpellContext, stmt: EmitAction) -> None:
        """Execute EMIT action."""
        data = {}
        if stmt.data:
            data = await self._eval_expr(ctx, stmt.data)

        ctx.add_trace(f"Emit: {stmt.event_type}")

        if not ctx.shadow_mode:
            await self.services.scheduler.emit_event(stmt.event_type, data)
        else:
            logger.debug(f"Shadow mode: would emit event {stmt.event_type}")

    async def _exec_log(self, ctx: SpellContext, stmt: LogAction) -> None:
        """Execute LOG action."""
        message = await self._eval_expr(ctx, stmt.message)
        message_str = str(message)

        ctx.add_trace(f"Log [{stmt.level}]: {message_str}")

        if stmt.level == "DEBUG":
            self.services.log_debug(message_str)
        elif stmt.level == "INFO":
            self.services.log_info(message_str)
        elif stmt.level == "OBSERVATION":
            self.services.log_observation(message_str)

    async def _exec_delta(self, ctx: SpellContext, stmt: DeltaAction) -> None:
        """Execute DELTA action."""
        ctx.add_trace(f"Delta: affects={stmt.affect_deltas} needs={stmt.need_deltas}")

        if not ctx.shadow_mode:
            if stmt.affect_deltas:
                self.services.thymos.apply_affect_delta(stmt.affect_deltas)
            if stmt.need_deltas:
                self.services.thymos.apply_need_delta(stmt.need_deltas)
        else:
            logger.debug(f"Shadow mode: would apply deltas")

    async def _exec_reset(self, ctx: SpellContext, stmt: ResetAction) -> None:
        """Execute RESET action."""
        ctx.add_trace(f"Reset: {stmt.target}")

        if ctx.shadow_mode:
            logger.debug(f"Shadow mode: would reset {stmt.target}")
            return

        target = stmt.target.upper()
        if target == "ALL":
            self.services.thymos.reset_affects()
            self.services.thymos.reset_needs()
        elif target == "AFFECTS":
            self.services.thymos.reset_affects()
        elif target == "NEEDS":
            self.services.thymos.reset_needs()
        else:
            # Specific affect or need name
            # Try affect first, then need
            try:
                self.services.thymos.reset_affect(stmt.target)
            except (KeyError, AttributeError):
                try:
                    self.services.thymos.reset_need(stmt.target)
                except (KeyError, AttributeError):
                    logger.warning(f"Unknown reset target: {stmt.target}")

    async def _exec_cast(self, ctx: SpellContext, stmt: CastStatement) -> None:
        """Execute CAST action (invoke another spell)."""
        ctx.add_trace(f"Cast: {stmt.spell_ref}")

        if self.services.load_spell is None:
            raise SpellError(f"Cannot CAST: no spell loader configured", stmt.line)

        # Load the referenced spell
        spell = await self.services.load_spell(stmt.spell_ref)
        if spell is None:
            raise SpellError(f"Spell not found: {stmt.spell_ref}", stmt.line)

        # Build context for the nested spell
        nested_context = {}
        if stmt.context:
            nested_context = await self._eval_expr(ctx, stmt.context)
            if not isinstance(nested_context, dict):
                nested_context = {"value": nested_context}

        # Execute the nested spell (inherits shadow mode)
        result = await self.cast(
            spell,
            event_data=nested_context,
            shadow_mode=ctx.shadow_mode,
            trace=ctx.trace_enabled,
        )

        # Store result in CAST_RESULT variable
        ctx.set_variable("CAST_RESULT", result)
        ctx.add_trace(f"Cast result: {result['status']}")

    # =========================================================================
    # AGENTIC ACTIONS
    # =========================================================================

    async def _exec_ask(self, ctx: SpellContext, stmt: AskStatement) -> None:
        """Execute ASK action."""
        question = await self._eval_expr(ctx, stmt.question)
        context_data = {}
        if stmt.context:
            context_data = await self._eval_expr(ctx, stmt.context)

        ctx.add_trace(f"Ask: {question}")

        if not ctx.shadow_mode:
            answer, reasoning = await self.services.agent.ask(str(question), context_data)
            ctx.set_variable(stmt.answer_var, answer)
            if stmt.reasoning_var:
                ctx.set_variable(stmt.reasoning_var, reasoning)
        else:
            logger.debug(f"Shadow mode: would ask '{question}'")
            ctx.set_variable(stmt.answer_var, False)
            if stmt.reasoning_var:
                ctx.set_variable(stmt.reasoning_var, "Shadow mode - no actual query")

    async def _exec_choose(self, ctx: SpellContext, stmt: ChooseStatement) -> None:
        """Execute CHOOSE action."""
        prompt = await self._eval_expr(ctx, stmt.prompt)
        context_data = {}
        if stmt.context:
            context_data = await self._eval_expr(ctx, stmt.context)

        options = [(k, v) for k, v in stmt.options.items()]
        ctx.add_trace(f"Choose: {prompt} from {[o[0] for o in options]}")

        if not ctx.shadow_mode:
            choice, reasoning = await self.services.agent.choose(str(prompt), options, context_data)
            ctx.set_variable(stmt.choice_var, choice)
            if stmt.reasoning_var:
                ctx.set_variable(stmt.reasoning_var, reasoning)
        else:
            logger.debug(f"Shadow mode: would choose from {options}")
            ctx.set_variable(stmt.choice_var, options[0][0] if options else "")
            if stmt.reasoning_var:
                ctx.set_variable(stmt.reasoning_var, "Shadow mode - default choice")

    async def _exec_rate(self, ctx: SpellContext, stmt: RateStatement) -> None:
        """Execute RATE action."""
        prompt = await self._eval_expr(ctx, stmt.prompt)
        context_data = {}
        if stmt.context:
            context_data = await self._eval_expr(ctx, stmt.context)

        ctx.add_trace(f"Rate: {prompt}")

        if not ctx.shadow_mode:
            rating, reasoning = await self.services.agent.rate(str(prompt), context_data)
            ctx.set_variable(stmt.rating_var, rating)
            if stmt.reasoning_var:
                ctx.set_variable(stmt.reasoning_var, reasoning)
        else:
            logger.debug(f"Shadow mode: would rate '{prompt}'")
            ctx.set_variable(stmt.rating_var, 0.5)
            if stmt.reasoning_var:
                ctx.set_variable(stmt.reasoning_var, "Shadow mode - default rating")

    async def _exec_generate(self, ctx: SpellContext, stmt: GenerateStatement) -> None:
        """Execute GENERATE action."""
        prompt = await self._eval_expr(ctx, stmt.prompt)
        context_data = {}
        if stmt.context:
            context_data = await self._eval_expr(ctx, stmt.context)

        ctx.add_trace(f"Generate: {prompt}")

        if not ctx.shadow_mode:
            content = await self.services.agent.generate(str(prompt), context_data)
            ctx.set_variable(stmt.output_var, content)
        else:
            logger.debug(f"Shadow mode: would generate from '{prompt}'")
            ctx.set_variable(stmt.output_var, "[Shadow mode - no generation]")

    async def _exec_reflect(self, ctx: SpellContext, stmt: ReflectStatement) -> None:
        """Execute REFLECT action."""
        prompt = await self._eval_expr(ctx, stmt.prompt)
        context_data = {}
        if stmt.context:
            context_data = await self._eval_expr(ctx, stmt.context)

        ctx.add_trace(f"Reflect: {prompt} save_as={stmt.save_as}")

        if not ctx.shadow_mode:
            reflection = await self.services.agent.reflect(str(prompt), context_data, stmt.save_as)
            ctx.set_variable("REFLECTION", reflection)
        else:
            logger.debug(f"Shadow mode: would reflect on '{prompt}'")
            ctx.set_variable("REFLECTION", "[Shadow mode - no reflection]")

    # =========================================================================
    # EXPRESSION EVALUATION
    # =========================================================================

    async def _eval_expr(self, ctx: SpellContext, expr: Expression) -> Any:
        """Evaluate an expression."""
        if isinstance(expr, Literal):
            return expr.value

        elif isinstance(expr, Variable):
            name = expr.name
            # Check variables first
            if ctx.has_variable(name):
                return ctx.get_variable(name)
            # Special variables
            if name == "NEEDS":
                return "NEEDS"
            if name == "AFFECTS":
                return "AFFECTS"
            if name == "need":
                return "need"
            if name == "affect":
                return "affect"
            # Unknown variable - return None
            return None

        elif isinstance(expr, PropertyAccess):
            base = await self._eval_expr(ctx, expr.base)

            # Handle need.xxx and affect.xxx
            if base == "need":
                return self.services.thymos.get_need(expr.property_name)
            if base == "affect":
                return self.services.thymos.get_affect(expr.property_name)

            # Handle object property access
            if isinstance(base, dict):
                return base.get(expr.property_name)
            if hasattr(base, expr.property_name):
                return getattr(base, expr.property_name)
            if hasattr(base, 'current') and expr.property_name == 'current':
                return base.current

            return None

        elif isinstance(expr, BinaryOp):
            left = await self._eval_expr(ctx, expr.left)
            right = await self._eval_expr(ctx, expr.right)
            return self._eval_binary_op(expr.operator, left, right)

        elif isinstance(expr, UnaryOp):
            operand = await self._eval_expr(ctx, expr.operand)
            return self._eval_unary_op(expr.operator, operand)

        elif isinstance(expr, FunctionCall):
            return await self._eval_function(ctx, expr)

        elif isinstance(expr, Interpolation):
            parts = []
            for part in expr.parts:
                val = await self._eval_expr(ctx, part)
                parts.append(str(val))
            return "".join(parts)

        else:
            raise SpellError(f"Unknown expression type: {type(expr).__name__}")

    def _eval_binary_op(self, op: str, left: Any, right: Any) -> Any:
        """Evaluate a binary operation."""
        # Logical
        if op == "AND":
            return bool(left) and bool(right)
        if op == "OR":
            return bool(left) or bool(right)

        # Comparison
        if op == "<":
            return left < right
        if op == "<=":
            return left <= right
        if op == ">":
            return left > right
        if op == ">=":
            return left >= right
        if op == "==" or op == "=":
            return left == right
        if op == "!=" or op == "<>":
            return left != right

        # Arithmetic
        if op == "+":
            return left + right
        if op == "-":
            return left - right
        if op == "*":
            return left * right
        if op == "/":
            return left / right if right != 0 else 0

        raise SpellError(f"Unknown operator: {op}")

    def _eval_unary_op(self, op: str, operand: Any) -> Any:
        """Evaluate a unary operation."""
        if op == "NOT":
            return not bool(operand)
        if op == "-":
            return -operand
        raise SpellError(f"Unknown unary operator: {op}")

    async def _eval_function(self, ctx: SpellContext, expr: FunctionCall) -> Any:
        """Evaluate a function call."""
        name = expr.function_name.upper()
        args = [await self._eval_expr(ctx, arg) for arg in expr.arguments]

        # Built-in functions
        if name == "COOLDOWN_READY":
            if len(args) < 2:
                raise SpellError("COOLDOWN_READY requires 2 arguments")
            return self.services.check_cooldown(str(args[0]), float(args[1]))

        if name == "SUGGESTED_ACTION":
            if len(args) < 1:
                raise SpellError("SUGGESTED_ACTION requires 1 argument")
            need_name = str(args[0])
            return self.services.thymos.get_care_action_for_need(need_name)

        if name == "ABS":
            return abs(args[0]) if args else 0

        if name == "MIN":
            return min(args) if args else 0

        if name == "MAX":
            return max(args) if args else 0

        if name == "LEN":
            return len(args[0]) if args else 0

        raise SpellError(f"Unknown function: {name}")
