"""
Grimoire Parser

Parses ThymosBASIC tokens into an AST.
"""

from typing import Optional, Callable
from .lexer import Lexer, Token, TokenType, LexerError
from .ast import (
    # Base
    ASTNode,
    Spell,
    SpellMetadata,
    SpellScope,
    # Statements
    Statement,
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
    QueueStatement,
    # Agentic
    AskStatement,
    ChooseStatement,
    RateStatement,
    GenerateStatement,
    ReflectStatement,
    # Triggers
    Trigger,
    NeedTrigger,
    AffectTrigger,
    EventTrigger,
    TimerTrigger,
    ManualTrigger,
    Comparison,
    # Imports
    ImportStatement,
    # Expressions
    Expression,
    BinaryOp,
    UnaryOp,
    Variable,
    Literal,
    PropertyAccess,
    FunctionCall,
    Interpolation,
)


class ParseError(Exception):
    """Error during parsing."""
    def __init__(self, message: str, token: Token):
        self.message = message
        self.token = token
        super().__init__(f"Line {token.line}, column {token.column}: {message}")


class Parser:
    """
    Recursive descent parser for ThymosBASIC.

    Usage:
        parser = Parser(source_code)
        spell = parser.parse()
    """

    def __init__(self, source: str):
        self.lexer = Lexer(source)
        self.tokens: list[Token] = []
        self.pos = 0
        self._tokenize()

    def _tokenize(self) -> None:
        """Tokenize the source into a list."""
        for token in self.lexer.tokenize(include_comments=False):
            self.tokens.append(token)

    def _current(self) -> Token:
        """Get current token."""
        if self.pos >= len(self.tokens):
            return self.tokens[-1]  # EOF
        return self.tokens[self.pos]

    def _peek(self, offset: int = 1) -> Token:
        """Peek ahead."""
        pos = self.pos + offset
        if pos >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[pos]

    def _advance(self) -> Token:
        """Advance and return current token."""
        token = self._current()
        self.pos += 1
        return token

    def _check(self, *types: TokenType) -> bool:
        """Check if current token is one of the given types."""
        return self._current().type in types

    def _match(self, *types: TokenType) -> Optional[Token]:
        """If current token matches, advance and return it."""
        if self._check(*types):
            return self._advance()
        return None

    def _expect(self, token_type: TokenType, message: str = "") -> Token:
        """Expect a specific token type, or raise error."""
        if self._check(token_type):
            return self._advance()
        msg = message or f"Expected {token_type.name}"
        raise ParseError(msg, self._current())

    def _skip_newlines(self) -> None:
        """Skip any newline tokens."""
        while self._match(TokenType.NEWLINE):
            pass

    def _at_end(self) -> bool:
        """Check if at end of tokens."""
        return self._check(TokenType.EOF)

    def _set_location(self, node: ASTNode, token: Token) -> ASTNode:
        """Set source location on an AST node."""
        return node.set_location(token.line, token.column)

    # =========================================================================
    # TOP-LEVEL PARSING
    # =========================================================================

    def parse(self) -> Spell:
        """Parse a complete spell."""
        self._skip_newlines()

        # Parse imports first
        imports = []
        while self._check(TokenType.IMPORT):
            imports.append(self._parse_import())
            self._skip_newlines()

        # Expect UNIT header
        start_token = self._expect(TokenType.UNIT, "Expected UNIT")
        name_token = self._expect(TokenType.IDENTIFIER, "Expected spell name")

        metadata = SpellMetadata(name=name_token.value)
        self._skip_newlines()

        # Parse metadata
        while self._check(TokenType.AUTHOR, TokenType.PRIORITY, TokenType.COOLDOWN,
                          TokenType.TAGS, TokenType.SCOPE):
            self._parse_metadata(metadata)
            self._skip_newlines()

        # Parse triggers
        triggers = []
        while self._check(TokenType.ON):
            triggers.append(self._parse_trigger())
            self._skip_newlines()

        # Parse body
        body = []
        labels = {}
        while not self._check(TokenType.END) and not self._at_end():
            stmt = self._parse_statement()
            if stmt:
                if isinstance(stmt, LabelStatement):
                    labels[stmt.label_name] = len(body)
                body.append(stmt)
            self._skip_newlines()

        # Expect END UNIT
        self._expect(TokenType.END, "Expected END UNIT")
        self._match(TokenType.UNIT)  # Optional UNIT after END

        spell = Spell(
            metadata=metadata,
            triggers=triggers,
            body=body,
            labels=labels,
            imports=imports,
        )
        return self._set_location(spell, start_token)

    def _parse_import(self) -> ImportStatement:
        """Parse IMPORT statement."""
        start = self._advance()  # IMPORT

        # Check for ACTION import
        import_type = "spell"
        if self._match(TokenType.ACTION):
            import_type = "action"

        path_token = self._expect(TokenType.STRING, "Expected import path")
        path = path_token.value

        alias = None
        if self._match(TokenType.AS):
            alias_token = self._expect(TokenType.IDENTIFIER, "Expected alias name")
            alias = alias_token.value

        stmt = ImportStatement(path=path, alias=alias, import_type=import_type)
        return self._set_location(stmt, start)

    def _parse_metadata(self, metadata: SpellMetadata) -> None:
        """Parse a metadata line."""
        if self._match(TokenType.AUTHOR):
            # Accept either identifier or string for author name
            if self._check(TokenType.STRING):
                token = self._advance()
            else:
                token = self._expect(TokenType.IDENTIFIER, "Expected author name")
            metadata.author = token.value
        elif self._match(TokenType.PRIORITY):
            token = self._expect(TokenType.NUMBER, "Expected priority number")
            metadata.priority = int(float(token.value))
        elif self._match(TokenType.COOLDOWN):
            token = self._expect(TokenType.NUMBER, "Expected cooldown minutes")
            metadata.cooldown_minutes = int(float(token.value))
        elif self._match(TokenType.TAGS):
            tags = []
            tags.append(self._expect(TokenType.IDENTIFIER, "Expected tag").value)
            while self._match(TokenType.COMMA):
                tags.append(self._expect(TokenType.IDENTIFIER, "Expected tag").value)
            metadata.tags = tags
        elif self._match(TokenType.SCOPE):
            # Parse scope flags
            scopes = set()
            scope_name = self._expect(TokenType.IDENTIFIER, "Expected scope name")
            scopes.add(self._scope_from_name(scope_name.value))
            while self._match(TokenType.COMMA):
                scope_name = self._expect(TokenType.IDENTIFIER, "Expected scope name")
                scopes.add(self._scope_from_name(scope_name.value))
            metadata.scope = scopes

    def _scope_from_name(self, name: str) -> SpellScope:
        """Convert scope name to SpellScope enum."""
        name_upper = name.upper()
        try:
            return SpellScope[name_upper]
        except KeyError:
            raise ParseError(f"Unknown scope: {name}", self._current())

    # =========================================================================
    # TRIGGERS
    # =========================================================================

    def _parse_trigger(self) -> Trigger:
        """Parse ON trigger."""
        start = self._advance()  # ON

        if self._match(TokenType.NEED):
            return self._parse_need_trigger(start)
        elif self._match(TokenType.AFFECT):
            return self._parse_affect_trigger(start)
        elif self._match(TokenType.EVENT):
            return self._parse_event_trigger(start)
        elif self._match(TokenType.TIMER):
            return self._parse_timer_trigger(start)
        elif self._match(TokenType.MANUAL):
            return self._parse_manual_trigger(start)
        else:
            raise ParseError("Expected trigger type after ON", self._current())

    def _parse_trigger_comparison(self) -> Comparison:
        """Parse comparison operator for triggers."""
        if self._match(TokenType.LT):
            return Comparison.LT
        elif self._match(TokenType.LE):
            return Comparison.LE
        elif self._match(TokenType.GT):
            return Comparison.GT
        elif self._match(TokenType.GE):
            return Comparison.GE
        elif self._match(TokenType.EQEQ):
            return Comparison.EQ
        elif self._match(TokenType.NE):
            return Comparison.NE
        else:
            raise ParseError("Expected comparison operator", self._current())

    def _parse_need_trigger(self, start: Token) -> NeedTrigger:
        """Parse ON need.<name> <op> <threshold>"""
        self._expect(TokenType.DOT, "Expected . after need")
        name = self._expect(TokenType.IDENTIFIER, "Expected need name")
        comp = self._parse_trigger_comparison()
        threshold = self._expect(TokenType.NUMBER, "Expected threshold")

        debounce = 0.0
        if self._match(TokenType.DEBOUNCE):
            debounce_token = self._expect(TokenType.NUMBER, "Expected debounce seconds")
            debounce = float(debounce_token.value)

        trigger = NeedTrigger(
            need_name=name.value,
            comparison=comp,
            threshold=float(threshold.value),
            debounce_seconds=debounce,
        )
        return self._set_location(trigger, start)

    def _parse_affect_trigger(self, start: Token) -> AffectTrigger:
        """Parse ON affect.<name> <op> <threshold>"""
        self._expect(TokenType.DOT, "Expected . after affect")
        name = self._expect(TokenType.IDENTIFIER, "Expected affect name")
        comp = self._parse_trigger_comparison()
        threshold = self._expect(TokenType.NUMBER, "Expected threshold")

        debounce = 0.0
        if self._match(TokenType.DEBOUNCE):
            debounce_token = self._expect(TokenType.NUMBER, "Expected debounce seconds")
            debounce = float(debounce_token.value)

        trigger = AffectTrigger(
            affect_name=name.value,
            comparison=comp,
            threshold=float(threshold.value),
            debounce_seconds=debounce,
        )
        return self._set_location(trigger, start)

    def _parse_event_trigger(self, start: Token) -> EventTrigger:
        """Parse ON event.<type> [WHERE <condition>]"""
        self._expect(TokenType.DOT, "Expected . after event")
        event_type = self._expect(TokenType.IDENTIFIER, "Expected event type")

        # Allow dotted event names like event.news.consumed
        full_type = event_type.value
        while self._match(TokenType.DOT):
            next_part = self._expect(TokenType.IDENTIFIER, "Expected event type part")
            full_type += "." + next_part.value

        condition = None
        if self._match(TokenType.WHERE):
            condition = self._parse_expression()

        trigger = EventTrigger(event_type=full_type, condition=condition)
        return self._set_location(trigger, start)

    def _parse_timer_trigger(self, start: Token) -> TimerTrigger:
        """Parse ON TIMER EVERY <n> or ON TIMER CRON '<expr>'"""
        if self._match(TokenType.EVERY):
            interval = self._expect(TokenType.NUMBER, "Expected interval")
            trigger = TimerTrigger(interval_minutes=float(interval.value))
        elif self._match(TokenType.CRON):
            cron = self._expect(TokenType.STRING, "Expected cron expression")
            trigger = TimerTrigger(cron_expr=cron.value)
        else:
            raise ParseError("Expected EVERY or CRON after TIMER", self._current())
        return self._set_location(trigger, start)

    def _parse_manual_trigger(self, start: Token) -> ManualTrigger:
        """Parse ON MANUAL '<label>'"""
        label = self._expect(TokenType.STRING, "Expected button label")
        trigger = ManualTrigger(label=label.value)
        return self._set_location(trigger, start)

    # =========================================================================
    # STATEMENTS
    # =========================================================================

    def _parse_statement(self) -> Optional[Statement]:
        """Parse a single statement."""
        self._skip_newlines()

        if self._at_end() or self._check(TokenType.END):
            return None

        start = self._current()

        # Label
        if self._check(TokenType.LABEL):
            return self._parse_label()

        # Control flow
        if self._check(TokenType.IF):
            return self._parse_if()
        if self._check(TokenType.FOR):
            return self._parse_for()
        if self._check(TokenType.WHILE):
            return self._parse_while()
        if self._check(TokenType.GOTO):
            return self._parse_goto()
        if self._check(TokenType.GOSUB):
            return self._parse_gosub()
        if self._check(TokenType.RETURN):
            return self._parse_return()
        if self._check(TokenType.EXIT):
            return self._parse_exit()
        if self._check(TokenType.WAIT):
            return self._parse_wait()
        if self._check(TokenType.CONTINUE):
            return self._parse_continue()
        if self._check(TokenType.BREAK):
            return self._parse_break()
        if self._check(TokenType.PARALLEL):
            return self._parse_parallel()

        # Actions
        if self._check(TokenType.LET):
            return self._parse_let()
        if self._check(TokenType.CARE):
            return self._parse_care()
        if self._check(TokenType.TASK):
            return self._parse_task()
        if self._check(TokenType.EMIT):
            return self._parse_emit()
        if self._check(TokenType.LOG):
            return self._parse_log()
        if self._check(TokenType.DELTA):
            return self._parse_delta()
        if self._check(TokenType.RESET):
            return self._parse_reset()
        if self._check(TokenType.CAST):
            return self._parse_cast()
        if self._check(TokenType.QUEUE):
            return self._parse_queue()

        # Agentic
        if self._check(TokenType.ASK):
            return self._parse_ask()
        if self._check(TokenType.CHOOSE):
            return self._parse_choose()
        if self._check(TokenType.RATE):
            return self._parse_rate()
        if self._check(TokenType.GENERATE):
            return self._parse_generate()
        if self._check(TokenType.REFLECT):
            return self._parse_reflect()

        raise ParseError(f"Unexpected token: {self._current().value}", self._current())

    # -------------------------------------------------------------------------
    # Control Flow Statements
    # -------------------------------------------------------------------------

    def _parse_label(self) -> LabelStatement:
        """Parse :label_name"""
        token = self._advance()  # LABEL token
        stmt = LabelStatement(label_name=token.value)
        return self._set_location(stmt, token)

    def _parse_if(self) -> IfStatement:
        """Parse IF ... THEN ... [ELSE IF ... THEN ...] [ELSE ...] END IF"""
        start = self._advance()  # IF
        condition = self._parse_expression()
        self._expect(TokenType.THEN, "Expected THEN after IF condition")
        self._skip_newlines()

        then_body = self._parse_block_until(TokenType.ELSE, TokenType.END)

        else_if_clauses = []
        else_body = []

        while self._check(TokenType.ELSE):
            self._advance()  # ELSE
            if self._match(TokenType.IF):
                # ELSE IF
                elif_condition = self._parse_expression()
                self._expect(TokenType.THEN, "Expected THEN after ELSE IF condition")
                self._skip_newlines()
                elif_body = self._parse_block_until(TokenType.ELSE, TokenType.END)
                else_if_clauses.append((elif_condition, elif_body))
            else:
                # ELSE (final)
                self._skip_newlines()
                else_body = self._parse_block_until(TokenType.END)
                break

        self._expect(TokenType.END, "Expected END IF")
        self._match(TokenType.IF)  # Optional IF after END

        stmt = IfStatement(
            condition=condition,
            then_body=then_body,
            else_if_clauses=else_if_clauses,
            else_body=else_body,
        )
        return self._set_location(stmt, start)

    def _parse_block_until(self, *terminators: TokenType) -> list[Statement]:
        """Parse statements until we hit a terminator."""
        body = []
        while not self._check(*terminators) and not self._at_end():
            stmt = self._parse_statement()
            if stmt:
                body.append(stmt)
            self._skip_newlines()
        return body

    def _parse_for(self) -> Statement:
        """Parse FOR EACH or FOR ... TO ..."""
        start = self._advance()  # FOR

        if self._match(TokenType.EACH):
            return self._parse_for_each(start)
        else:
            return self._parse_for_to(start)

    def _parse_for_each(self, start: Token) -> ForEachStatement:
        """Parse FOR EACH $item IN <collection> [WHERE <condition>]"""
        var_token = self._expect(TokenType.VARIABLE, "Expected variable")
        self._expect(TokenType.IN, "Expected IN")
        collection = self._parse_expression()

        filter_cond = None
        if self._match(TokenType.WHERE):
            filter_cond = self._parse_expression()

        self._skip_newlines()
        body = self._parse_block_until(TokenType.NEXT)
        self._expect(TokenType.NEXT, "Expected NEXT")
        self._match(TokenType.VARIABLE)  # Optional $var after NEXT

        stmt = ForEachStatement(
            item_var=var_token.value,
            collection=collection,
            filter_condition=filter_cond,
            body=body,
        )
        return self._set_location(stmt, start)

    def _parse_for_to(self, start: Token) -> ForStatement:
        """Parse FOR $i = <start> TO <end> [STEP <step>]"""
        var_token = self._expect(TokenType.VARIABLE, "Expected variable")
        self._expect(TokenType.EQ, "Expected =")
        start_expr = self._parse_expression()
        self._expect(TokenType.TO, "Expected TO")
        end_expr = self._parse_expression()

        step_expr = None
        if self._match(TokenType.STEP):
            step_expr = self._parse_expression()

        self._skip_newlines()
        body = self._parse_block_until(TokenType.NEXT)
        self._expect(TokenType.NEXT, "Expected NEXT")
        self._match(TokenType.VARIABLE)  # Optional $var after NEXT

        stmt = ForStatement(
            var_name=var_token.value,
            start=start_expr,
            end=end_expr,
            step=step_expr,
            body=body,
        )
        return self._set_location(stmt, start)

    def _parse_while(self) -> WhileStatement:
        """Parse WHILE <condition> ... END WHILE"""
        start = self._advance()  # WHILE
        condition = self._parse_expression()
        self._skip_newlines()

        body = self._parse_block_until(TokenType.END)
        self._expect(TokenType.END, "Expected END WHILE")
        self._match(TokenType.WHILE)

        stmt = WhileStatement(condition=condition, body=body)
        return self._set_location(stmt, start)

    def _parse_goto(self) -> GotoStatement:
        """Parse GOTO label"""
        start = self._advance()  # GOTO
        label = self._expect(TokenType.IDENTIFIER, "Expected label name")
        stmt = GotoStatement(target_label=label.value)
        return self._set_location(stmt, start)

    def _parse_gosub(self) -> GosubStatement:
        """Parse GOSUB label"""
        start = self._advance()  # GOSUB
        label = self._expect(TokenType.IDENTIFIER, "Expected label name")
        stmt = GosubStatement(target_label=label.value)
        return self._set_location(stmt, start)

    def _parse_return(self) -> ReturnStatement:
        """Parse RETURN"""
        start = self._advance()  # RETURN
        stmt = ReturnStatement()
        return self._set_location(stmt, start)

    def _parse_exit(self) -> ExitStatement:
        """Parse EXIT SUCCESS|FAILURE|SKIPPED ['reason']"""
        start = self._advance()  # EXIT

        status = "SUCCESS"
        if self._match(TokenType.SUCCESS):
            status = "SUCCESS"
        elif self._match(TokenType.FAILURE):
            status = "FAILURE"
        elif self._match(TokenType.SKIPPED):
            status = "SKIPPED"

        reason = None
        if self._check(TokenType.STRING):
            reason = self._advance().value

        stmt = ExitStatement(status=status, reason=reason)
        return self._set_location(stmt, start)

    def _parse_wait(self) -> WaitStatement:
        """Parse WAIT <seconds>"""
        start = self._advance()  # WAIT
        seconds = self._parse_expression()
        stmt = WaitStatement(seconds=seconds)
        return self._set_location(stmt, start)

    def _parse_continue(self) -> ContinueStatement:
        """Parse CONTINUE"""
        start = self._advance()
        stmt = ContinueStatement()
        return self._set_location(stmt, start)

    def _parse_break(self) -> BreakStatement:
        """Parse BREAK"""
        start = self._advance()
        stmt = BreakStatement()
        return self._set_location(stmt, start)

    def _parse_parallel(self) -> ParallelBlock:
        """Parse PARALLEL ... END PARALLEL"""
        start = self._advance()  # PARALLEL
        self._skip_newlines()

        branches = []
        current_branch = []

        while not self._check(TokenType.END) and not self._at_end():
            if self._match(TokenType.BRANCH):
                self._match(TokenType.COLON)  # Optional :
                if current_branch:
                    branches.append(current_branch)
                current_branch = []
            else:
                stmt = self._parse_statement()
                if stmt:
                    current_branch.append(stmt)
            self._skip_newlines()

        if current_branch:
            branches.append(current_branch)

        self._expect(TokenType.END, "Expected END PARALLEL")
        self._match(TokenType.PARALLEL)

        wait_mode = "ALL"
        if self._match(TokenType.WAIT):
            if self._match(TokenType.ALL):
                wait_mode = "ALL"
            elif self._match(TokenType.IDENTIFIER):  # FIRST
                wait_mode = "FIRST"

        stmt = ParallelBlock(branches=branches, wait_mode=wait_mode)
        return self._set_location(stmt, start)

    # -------------------------------------------------------------------------
    # Action Statements
    # -------------------------------------------------------------------------

    def _parse_let(self) -> LetStatement:
        """Parse LET $name = <expression>"""
        start = self._advance()  # LET
        var_token = self._expect(TokenType.VARIABLE, "Expected variable")
        self._expect(TokenType.EQ, "Expected =")
        value = self._parse_expression()
        stmt = LetStatement(var_name=var_token.value, value=value)
        return self._set_location(stmt, start)

    def _parse_care(self) -> CareAction:
        """Parse CARE <action_key> or CARE FOR $need"""
        start = self._advance()  # CARE

        if self._match(TokenType.FOR):
            for_need = self._parse_expression()
            stmt = CareAction(for_need=for_need)
        else:
            action_key = self._expect(TokenType.IDENTIFIER, "Expected care action key")
            stmt = CareAction(action_key=action_key.value)

        return self._set_location(stmt, start)

    def _parse_task(self) -> TaskAction:
        """Parse TASK <action> [param=value, ...] [AWAIT]"""
        start = self._advance()  # TASK
        action = self._advance()  # action name (identifier or keyword)
        full_action = action.value

        # Allow dotted action names, but stop if next would be param=value
        while self._check(TokenType.DOT):
            # Peek ahead to see if after the dot we have param=value pattern
            next_tok = self._peek(1)
            next_next = self._peek(2)
            if next_next.type == TokenType.EQ:
                # This dot leads to a param assignment, stop here
                break
            self._advance()  # consume DOT
            # Accept identifier or keyword as action part
            next_part = self._advance()
            full_action += "." + next_part.value

        # Parse parameters
        params = {}
        while self._check(TokenType.IDENTIFIER) and self._peek().type == TokenType.EQ:
            param_name = self._advance().value
            self._advance()  # =
            param_value = self._parse_expression()
            params[param_name] = param_value
            self._match(TokenType.COMMA)

        await_completion = self._match(TokenType.AWAIT) is not None

        stmt = TaskAction(action=full_action, parameters=params, await_completion=await_completion)
        return self._set_location(stmt, start)

    def _parse_emit(self) -> EmitAction:
        """Parse EMIT <event_type> [WITH <data>]"""
        start = self._advance()  # EMIT
        event_type = self._expect(TokenType.IDENTIFIER, "Expected event type")

        # Allow dotted event names
        full_type = event_type.value
        while self._match(TokenType.DOT):
            next_part = self._expect(TokenType.IDENTIFIER, "Expected event type part")
            full_type += "." + next_part.value

        data = None
        if self._match(TokenType.WITH):
            data = self._parse_expression()

        stmt = EmitAction(event_type=full_type, data=data)
        return self._set_location(stmt, start)

    def _parse_log(self) -> LogAction:
        """Parse LOG DEBUG|INFO|OBSERVATION '<message>'"""
        start = self._advance()  # LOG

        level = "INFO"
        if self._match(TokenType.DEBUG):
            level = "DEBUG"
        elif self._match(TokenType.INFO):
            level = "INFO"
        elif self._match(TokenType.OBSERVATION):
            level = "OBSERVATION"

        message = self._parse_expression()
        stmt = LogAction(level=level, message=message)
        return self._set_location(stmt, start)

    def _parse_delta(self) -> DeltaAction:
        """Parse DELTA affect.x +0.1, need.y +0.2"""
        start = self._advance()  # DELTA

        affect_deltas = {}
        need_deltas = {}

        while True:
            if self._match(TokenType.AFFECT):
                self._expect(TokenType.DOT, "Expected .")
                name = self._expect(TokenType.IDENTIFIER, "Expected affect name")
                value = self._parse_number_with_sign()
                affect_deltas[name.value] = value
            elif self._match(TokenType.NEED):
                self._expect(TokenType.DOT, "Expected .")
                name = self._expect(TokenType.IDENTIFIER, "Expected need name")
                value = self._parse_number_with_sign()
                need_deltas[name.value] = value
            else:
                break

            if not self._match(TokenType.COMMA):
                break

        stmt = DeltaAction(affect_deltas=affect_deltas, need_deltas=need_deltas)
        return self._set_location(stmt, start)

    def _parse_number_with_sign(self) -> float:
        """Parse a number that may have + or - prefix."""
        sign = 1.0
        if self._match(TokenType.PLUS):
            sign = 1.0
        elif self._match(TokenType.MINUS):
            sign = -1.0
        num = self._expect(TokenType.NUMBER, "Expected number")
        return sign * float(num.value)

    def _parse_reset(self) -> ResetAction:
        """Parse RESET ALL|AFFECTS|NEEDS|<name>"""
        start = self._advance()  # RESET

        if self._match(TokenType.ALL):
            target = "ALL"
        elif self._match(TokenType.AFFECTS):
            target = "AFFECTS"
        elif self._match(TokenType.NEEDS):
            target = "NEEDS"
        else:
            target = self._expect(TokenType.IDENTIFIER, "Expected reset target").value

        stmt = ResetAction(target=target)
        return self._set_location(stmt, start)

    def _parse_cast(self) -> CastStatement:
        """Parse CAST <spell_ref> [WITH <context>]"""
        start = self._advance()  # CAST
        spell_ref = self._expect(TokenType.IDENTIFIER, "Expected spell name or alias")

        context = None
        if self._match(TokenType.WITH):
            context = self._parse_expression()

        stmt = CastStatement(spell_ref=spell_ref.value, context=context)
        return self._set_location(stmt, start)

    def _parse_queue(self) -> QueueStatement:
        """Parse QUEUE <action> FOR PHASE <phase> [PRIORITY <n>]"""
        start = self._advance()  # QUEUE

        # Parse action name (may be dotted like session.research)
        action_token = self._advance()
        action = action_token.value
        while self._check(TokenType.DOT):
            self._advance()  # consume DOT
            next_part = self._advance()
            action += "." + next_part.value

        # Parse optional parameters before FOR
        params = {}
        while self._check(TokenType.IDENTIFIER) and self._peek().type == TokenType.EQ:
            param_name = self._advance().value
            self._advance()  # =
            param_value = self._parse_expression()
            params[param_name] = param_value
            self._match(TokenType.COMMA)

        # Expect FOR PHASE
        self._expect(TokenType.FOR, "Expected FOR after action in QUEUE statement")
        self._expect(TokenType.PHASE, "Expected PHASE after FOR in QUEUE statement")

        # Parse phase name (morning, afternoon, evening, night)
        phase_token = self._expect(TokenType.IDENTIFIER, "Expected phase name (morning, afternoon, evening, night)")
        phase = phase_token.value.lower()

        # Optional PRIORITY
        priority = 1
        if self._check(TokenType.PRIORITY):
            self._advance()  # PRIORITY
            priority_token = self._expect(TokenType.NUMBER, "Expected priority number")
            priority = int(float(priority_token.value))

        stmt = QueueStatement(action=action, phase=phase, priority=priority, parameters=params)
        return self._set_location(stmt, start)

    # -------------------------------------------------------------------------
    # Agentic Statements
    # -------------------------------------------------------------------------

    def _parse_ask(self) -> AskStatement:
        """Parse ASK '<question>' [WITH <context>] INTO $answer[, $reasoning]"""
        start = self._advance()  # ASK
        question = self._parse_expression()

        context = None
        if self._match(TokenType.WITH):
            context = self._parse_expression()

        self._expect(TokenType.INTO, "Expected INTO")
        answer_var = self._expect(TokenType.VARIABLE, "Expected variable").value

        reasoning_var = None
        if self._match(TokenType.COMMA):
            reasoning_var = self._expect(TokenType.VARIABLE, "Expected variable").value

        stmt = AskStatement(
            question=question,
            context=context,
            answer_var=answer_var,
            reasoning_var=reasoning_var,
        )
        return self._set_location(stmt, start)

    def _parse_choose(self) -> ChooseStatement:
        """Parse CHOOSE '<prompt>' FROM opt1='Label 1', ... [WITH <context>] INTO $choice[, $reasoning]"""
        start = self._advance()  # CHOOSE
        prompt = self._parse_expression()

        self._expect(TokenType.FROM, "Expected FROM")
        options = {}
        while True:
            opt_id = self._expect(TokenType.IDENTIFIER, "Expected option ID")
            self._expect(TokenType.EQ, "Expected =")
            opt_label = self._expect(TokenType.STRING, "Expected option label")
            options[opt_id.value] = opt_label.value
            if not self._match(TokenType.COMMA):
                break
            # Check if next is WITH or INTO, not another option
            if self._check(TokenType.WITH, TokenType.INTO):
                break

        context = None
        if self._match(TokenType.WITH):
            context = self._parse_expression()

        self._expect(TokenType.INTO, "Expected INTO")
        choice_var = self._expect(TokenType.VARIABLE, "Expected variable").value

        reasoning_var = None
        if self._match(TokenType.COMMA):
            reasoning_var = self._expect(TokenType.VARIABLE, "Expected variable").value

        stmt = ChooseStatement(
            prompt=prompt,
            options=options,
            context=context,
            choice_var=choice_var,
            reasoning_var=reasoning_var,
        )
        return self._set_location(stmt, start)

    def _parse_rate(self) -> RateStatement:
        """Parse RATE '<prompt>' [WITH <context>] INTO $rating[, $reasoning]"""
        start = self._advance()  # RATE
        prompt = self._parse_expression()

        context = None
        if self._match(TokenType.WITH):
            context = self._parse_expression()

        self._expect(TokenType.INTO, "Expected INTO")
        rating_var = self._expect(TokenType.VARIABLE, "Expected variable").value

        reasoning_var = None
        if self._match(TokenType.COMMA):
            reasoning_var = self._expect(TokenType.VARIABLE, "Expected variable").value

        stmt = RateStatement(
            prompt=prompt,
            context=context,
            rating_var=rating_var,
            reasoning_var=reasoning_var,
        )
        return self._set_location(stmt, start)

    def _parse_generate(self) -> GenerateStatement:
        """Parse GENERATE '<prompt>' [WITH <context>] INTO $content"""
        start = self._advance()  # GENERATE
        prompt = self._parse_expression()

        context = None
        if self._match(TokenType.WITH):
            context = self._parse_expression()

        self._expect(TokenType.INTO, "Expected INTO")
        output_var = self._expect(TokenType.VARIABLE, "Expected variable").value

        stmt = GenerateStatement(prompt=prompt, context=context, output_var=output_var)
        return self._set_location(stmt, start)

    def _parse_reflect(self) -> ReflectStatement:
        """Parse REFLECT '<prompt>' [WITH <context>] [SAVE AS JOURNAL|OBSERVATION]"""
        start = self._advance()  # REFLECT
        prompt = self._parse_expression()

        context = None
        if self._match(TokenType.WITH):
            context = self._parse_expression()

        save_as = None
        if self._match(TokenType.SAVE):
            self._expect(TokenType.AS, "Expected AS after SAVE")
            if self._match(TokenType.JOURNAL):
                save_as = "JOURNAL"
            elif self._match(TokenType.OBSERVATION):
                save_as = "OBSERVATION"
            else:
                raise ParseError("Expected JOURNAL or OBSERVATION", self._current())

        stmt = ReflectStatement(prompt=prompt, context=context, save_as=save_as)
        return self._set_location(stmt, start)

    # =========================================================================
    # EXPRESSIONS
    # =========================================================================

    def _parse_expression(self) -> Expression:
        """Parse an expression (entry point)."""
        return self._parse_or()

    def _parse_or(self) -> Expression:
        """Parse OR expressions."""
        left = self._parse_and()
        while self._match(TokenType.OR):
            right = self._parse_and()
            left = BinaryOp(left=left, operator="OR", right=right)
        return left

    def _parse_and(self) -> Expression:
        """Parse AND expressions."""
        left = self._parse_not()
        while self._match(TokenType.AND):
            right = self._parse_not()
            left = BinaryOp(left=left, operator="AND", right=right)
        return left

    def _parse_not(self) -> Expression:
        """Parse NOT expressions."""
        if self._match(TokenType.NOT):
            operand = self._parse_not()
            return UnaryOp(operator="NOT", operand=operand)
        return self._parse_comparison()

    def _parse_comparison(self) -> Expression:
        """Parse comparison expressions."""
        left = self._parse_additive()

        if self._check(TokenType.LT, TokenType.LE, TokenType.GT, TokenType.GE,
                       TokenType.EQEQ, TokenType.NE):
            op_token = self._advance()
            right = self._parse_additive()
            return BinaryOp(left=left, operator=op_token.value, right=right)

        return left

    def _parse_additive(self) -> Expression:
        """Parse + and - expressions."""
        left = self._parse_multiplicative()
        while self._check(TokenType.PLUS, TokenType.MINUS):
            op = self._advance()
            right = self._parse_multiplicative()
            left = BinaryOp(left=left, operator=op.value, right=right)
        return left

    def _parse_multiplicative(self) -> Expression:
        """Parse * and / expressions."""
        left = self._parse_unary()
        while self._check(TokenType.STAR, TokenType.SLASH):
            op = self._advance()
            right = self._parse_unary()
            left = BinaryOp(left=left, operator=op.value, right=right)
        return left

    def _parse_unary(self) -> Expression:
        """Parse unary - expressions."""
        if self._match(TokenType.MINUS):
            operand = self._parse_unary()
            return UnaryOp(operator="-", operand=operand)
        return self._parse_postfix()

    def _parse_postfix(self) -> Expression:
        """Parse postfix expressions (property access, function calls)."""
        expr = self._parse_primary()

        while True:
            if self._match(TokenType.DOT):
                prop = self._expect(TokenType.IDENTIFIER, "Expected property name")
                expr = PropertyAccess(base=expr, property_name=prop.value)
            elif self._match(TokenType.LPAREN):
                # Function call
                if isinstance(expr, Variable) or isinstance(expr, PropertyAccess):
                    args = []
                    if not self._check(TokenType.RPAREN):
                        args.append(self._parse_expression())
                        while self._match(TokenType.COMMA):
                            args.append(self._parse_expression())
                    self._expect(TokenType.RPAREN, "Expected )")

                    if isinstance(expr, Variable):
                        expr = FunctionCall(function_name=expr.name, arguments=args)
                    else:
                        # PropertyAccess as function - convert to FunctionCall
                        # e.g., obj.method() - for now just keep as is
                        raise ParseError("Method calls not yet supported", self._current())
                else:
                    raise ParseError("Cannot call non-function", self._current())
            else:
                break

        return expr

    def _parse_primary(self) -> Expression:
        """Parse primary expressions (literals, variables, parenthesized)."""
        token = self._current()

        # Numbers
        if self._check(TokenType.NUMBER):
            self._advance()
            return Literal(value=float(token.value), literal_type="number")

        # Strings
        if self._check(TokenType.STRING):
            self._advance()
            # Check for interpolation
            if "{" in token.value:
                return self._parse_interpolated_string(token.value)
            return Literal(value=token.value, literal_type="string")

        # Booleans
        if self._match(TokenType.TRUE):
            return Literal(value=True, literal_type="boolean")
        if self._match(TokenType.FALSE):
            return Literal(value=False, literal_type="boolean")

        # Variables
        if self._check(TokenType.VARIABLE):
            self._advance()
            return Variable(name=token.value)

        # Keywords that act as values
        if self._check(TokenType.NEEDS):
            self._advance()
            return Variable(name="NEEDS")
        if self._check(TokenType.AFFECTS):
            self._advance()
            return Variable(name="AFFECTS")

        # Identifiers (for property access chains like need.value_coherence)
        if self._check(TokenType.NEED):
            self._advance()
            return Variable(name="need")
        if self._check(TokenType.AFFECT):
            self._advance()
            return Variable(name="affect")
        if self._check(TokenType.IDENTIFIER):
            self._advance()
            return Variable(name=token.value)

        # Parenthesized expression
        if self._match(TokenType.LPAREN):
            expr = self._parse_expression()
            self._expect(TokenType.RPAREN, "Expected )")
            return expr

        raise ParseError(f"Unexpected token in expression: {token.value}", token)

    def _parse_interpolated_string(self, s: str) -> Expression:
        """Parse a string with {interpolation} into an Interpolation node."""
        parts = []
        current = []
        i = 0

        while i < len(s):
            if s[i] == "{":
                # Start of interpolation
                if current:
                    parts.append(Literal(value="".join(current), literal_type="string"))
                    current = []
                i += 1
                # Find matching }
                expr_chars = []
                depth = 1
                while i < len(s) and depth > 0:
                    if s[i] == "{":
                        depth += 1
                    elif s[i] == "}":
                        depth -= 1
                        if depth == 0:
                            break
                    expr_chars.append(s[i])
                    i += 1
                i += 1  # Skip closing }
                # Parse the expression inside
                expr_str = "".join(expr_chars)
                sub_parser = Parser(expr_str)
                sub_parser._tokenize()
                # Remove EOF
                sub_parser.tokens = [t for t in sub_parser.tokens if t.type != TokenType.EOF]
                sub_parser.tokens.append(Token(TokenType.EOF, "", 0, 0))
                parts.append(sub_parser._parse_expression())
            else:
                current.append(s[i])
                i += 1

        if current:
            parts.append(Literal(value="".join(current), literal_type="string"))

        if len(parts) == 1 and isinstance(parts[0], Literal):
            return parts[0]

        return Interpolation(parts=parts)
