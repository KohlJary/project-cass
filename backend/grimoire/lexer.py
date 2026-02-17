"""
Grimoire Lexer (Tokenizer)

Converts ThymosBASIC source code into a stream of tokens.
"""

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Iterator, Optional


class TokenType(Enum):
    """Token types for ThymosBASIC."""
    # Literals
    NUMBER = auto()
    STRING = auto()
    TRUE = auto()
    FALSE = auto()

    # Identifiers and variables
    IDENTIFIER = auto()
    VARIABLE = auto()        # $name

    # Keywords - Structure
    UNIT = auto()
    END = auto()
    AUTHOR = auto()
    PRIORITY = auto()
    COOLDOWN = auto()
    TAGS = auto()
    SCOPE = auto()
    IMPORT = auto()
    AS = auto()
    ACTION = auto()

    # Keywords - Triggers
    ON = auto()
    NEED = auto()
    AFFECT = auto()
    EVENT = auto()
    TIMER = auto()
    EVERY = auto()
    CRON = auto()
    MANUAL = auto()
    DEBOUNCE = auto()
    WHERE = auto()

    # Keywords - Control Flow
    IF = auto()
    THEN = auto()
    ELSE = auto()
    FOR = auto()
    EACH = auto()
    IN = auto()
    TO = auto()
    STEP = auto()
    NEXT = auto()
    WHILE = auto()
    GOTO = auto()
    GOSUB = auto()
    RETURN = auto()
    EXIT = auto()
    WAIT = auto()
    CONTINUE = auto()
    BREAK = auto()
    PARALLEL = auto()
    BRANCH = auto()

    # Keywords - Actions
    LET = auto()
    CARE = auto()
    TASK = auto()
    AWAIT = auto()
    EMIT = auto()
    LOG = auto()
    DELTA = auto()
    RESET = auto()
    CAST = auto()
    WITH = auto()
    INTO = auto()

    # Keywords - Agentic
    ASK = auto()
    CHOOSE = auto()
    FROM = auto()
    RATE = auto()
    GENERATE = auto()
    REFLECT = auto()
    SAVE = auto()

    # Keywords - Levels/Status
    DEBUG = auto()
    INFO = auto()
    OBSERVATION = auto()
    SUCCESS = auto()
    FAILURE = auto()
    SKIPPED = auto()
    JOURNAL = auto()

    # Keywords - Collections
    NEEDS = auto()
    AFFECTS = auto()
    ALL = auto()

    # Keywords - Logic
    AND = auto()
    OR = auto()
    NOT = auto()

    # Operators
    PLUS = auto()           # +
    MINUS = auto()          # -
    STAR = auto()           # *
    SLASH = auto()          # /
    LT = auto()             # <
    LE = auto()             # <=
    GT = auto()             # >
    GE = auto()             # >=
    EQ = auto()             # = (assignment) or == (comparison)
    EQEQ = auto()           # ==
    NE = auto()             # != or <>
    DOT = auto()            # .

    # Delimiters
    LPAREN = auto()         # (
    RPAREN = auto()         # )
    LBRACKET = auto()       # [
    RBRACKET = auto()       # ]
    COMMA = auto()          # ,
    COLON = auto()          # :
    UNDERSCORE = auto()     # _ (line continuation)

    # Special
    NEWLINE = auto()
    EOF = auto()
    COMMENT = auto()        # ' comment (usually skipped)
    LABEL = auto()          # :label_name


@dataclass
class Token:
    """A single token from the source code."""
    type: TokenType
    value: str
    line: int
    column: int

    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.value!r}, L{self.line}:{self.column})"


# Keyword mapping
KEYWORDS: dict[str, TokenType] = {
    "UNIT": TokenType.UNIT,
    "END": TokenType.END,
    "AUTHOR": TokenType.AUTHOR,
    "PRIORITY": TokenType.PRIORITY,
    "COOLDOWN": TokenType.COOLDOWN,
    "TAGS": TokenType.TAGS,
    "SCOPE": TokenType.SCOPE,
    "IMPORT": TokenType.IMPORT,
    "AS": TokenType.AS,
    "ACTION": TokenType.ACTION,
    "ON": TokenType.ON,
    "NEED": TokenType.NEED,
    "AFFECT": TokenType.AFFECT,
    "EVENT": TokenType.EVENT,
    "TIMER": TokenType.TIMER,
    "EVERY": TokenType.EVERY,
    "CRON": TokenType.CRON,
    "MANUAL": TokenType.MANUAL,
    "DEBOUNCE": TokenType.DEBOUNCE,
    "WHERE": TokenType.WHERE,
    "IF": TokenType.IF,
    "THEN": TokenType.THEN,
    "ELSE": TokenType.ELSE,
    "FOR": TokenType.FOR,
    "EACH": TokenType.EACH,
    "IN": TokenType.IN,
    "TO": TokenType.TO,
    "STEP": TokenType.STEP,
    "NEXT": TokenType.NEXT,
    "WHILE": TokenType.WHILE,
    "GOTO": TokenType.GOTO,
    "GOSUB": TokenType.GOSUB,
    "RETURN": TokenType.RETURN,
    "EXIT": TokenType.EXIT,
    "WAIT": TokenType.WAIT,
    "CONTINUE": TokenType.CONTINUE,
    "BREAK": TokenType.BREAK,
    "PARALLEL": TokenType.PARALLEL,
    "BRANCH": TokenType.BRANCH,
    "LET": TokenType.LET,
    "CARE": TokenType.CARE,
    "TASK": TokenType.TASK,
    "AWAIT": TokenType.AWAIT,
    "EMIT": TokenType.EMIT,
    "LOG": TokenType.LOG,
    "DELTA": TokenType.DELTA,
    "RESET": TokenType.RESET,
    "CAST": TokenType.CAST,
    "WITH": TokenType.WITH,
    "INTO": TokenType.INTO,
    "ASK": TokenType.ASK,
    "CHOOSE": TokenType.CHOOSE,
    "FROM": TokenType.FROM,
    "RATE": TokenType.RATE,
    "GENERATE": TokenType.GENERATE,
    "REFLECT": TokenType.REFLECT,
    "SAVE": TokenType.SAVE,
    "DEBUG": TokenType.DEBUG,
    "INFO": TokenType.INFO,
    "OBSERVATION": TokenType.OBSERVATION,
    "SUCCESS": TokenType.SUCCESS,
    "FAILURE": TokenType.FAILURE,
    "SKIPPED": TokenType.SKIPPED,
    "JOURNAL": TokenType.JOURNAL,
    "NEEDS": TokenType.NEEDS,
    "AFFECTS": TokenType.AFFECTS,
    "ALL": TokenType.ALL,
    "AND": TokenType.AND,
    "OR": TokenType.OR,
    "NOT": TokenType.NOT,
    "TRUE": TokenType.TRUE,
    "FALSE": TokenType.FALSE,
}


class LexerError(Exception):
    """Error during lexical analysis."""
    def __init__(self, message: str, line: int, column: int):
        self.message = message
        self.line = line
        self.column = column
        super().__init__(f"Line {line}, column {column}: {message}")


class Lexer:
    """
    Tokenizer for ThymosBASIC.

    Usage:
        lexer = Lexer(source_code)
        for token in lexer.tokenize():
            print(token)
    """

    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.column = 1
        self.line_start = 0  # Position of current line start

    def _current(self) -> str:
        """Get current character."""
        if self.pos >= len(self.source):
            return ""
        return self.source[self.pos]

    def _peek(self, offset: int = 1) -> str:
        """Peek ahead."""
        pos = self.pos + offset
        if pos >= len(self.source):
            return ""
        return self.source[pos]

    def _advance(self) -> str:
        """Advance and return current character."""
        char = self._current()
        self.pos += 1
        if char == "\n":
            self.line += 1
            self.column = 1
            self.line_start = self.pos
        else:
            self.column += 1
        return char

    def _skip_whitespace(self) -> None:
        """Skip whitespace (but not newlines - they're significant)."""
        while self._current() in " \t\r":
            self._advance()

    def _skip_line_continuation(self) -> bool:
        """Handle _ at end of line (continuation)."""
        if self._current() == "_":
            # Must be followed by optional whitespace and newline
            save_pos = self.pos
            save_line = self.line
            save_col = self.column
            self._advance()  # Skip _
            self._skip_whitespace()
            if self._current() == "\n":
                self._advance()  # Skip newline
                self._skip_whitespace()  # Skip leading whitespace on next line
                return True
            # Not a continuation, restore
            self.pos = save_pos
            self.line = save_line
            self.column = save_col
        return False

    def _read_string(self, quote: str) -> Token:
        """Read a string literal."""
        start_line = self.line
        start_col = self.column
        self._advance()  # Skip opening quote
        value = []

        while self._current() and self._current() != quote:
            if self._current() == "\n":
                raise LexerError("Unterminated string", start_line, start_col)
            if self._current() == "\\" and self._peek() in (quote, "\\", "n", "t", "{", "}"):
                self._advance()  # Skip backslash
                escaped = self._advance()
                if escaped == "n":
                    value.append("\n")
                elif escaped == "t":
                    value.append("\t")
                else:
                    value.append(escaped)
            else:
                value.append(self._advance())

        if not self._current():
            raise LexerError("Unterminated string", start_line, start_col)

        self._advance()  # Skip closing quote
        return Token(TokenType.STRING, "".join(value), start_line, start_col)

    def _read_number(self) -> Token:
        """Read a number literal."""
        start_line = self.line
        start_col = self.column
        value = []

        # Handle negative numbers
        if self._current() == "-":
            value.append(self._advance())

        # Integer part
        while self._current().isdigit():
            value.append(self._advance())

        # Decimal part
        if self._current() == "." and self._peek().isdigit():
            value.append(self._advance())  # .
            while self._current().isdigit():
                value.append(self._advance())

        return Token(TokenType.NUMBER, "".join(value), start_line, start_col)

    def _read_identifier_or_keyword(self) -> Token:
        """Read an identifier or keyword."""
        start_line = self.line
        start_col = self.column
        value = []

        while self._current() and (self._current().isalnum() or self._current() == "_"):
            value.append(self._advance())

        text = "".join(value)
        upper = text.upper()

        # Check if it's a keyword
        if upper in KEYWORDS:
            return Token(KEYWORDS[upper], text, start_line, start_col)

        return Token(TokenType.IDENTIFIER, text, start_line, start_col)

    def _read_variable(self) -> Token:
        """Read a variable ($name)."""
        start_line = self.line
        start_col = self.column
        self._advance()  # Skip $
        value = []

        while self._current() and (self._current().isalnum() or self._current() == "_"):
            value.append(self._advance())

        if not value:
            raise LexerError("Expected variable name after $", start_line, start_col)

        return Token(TokenType.VARIABLE, "".join(value), start_line, start_col)

    def _read_comment(self) -> Token:
        """Read a comment (everything after ')."""
        start_line = self.line
        start_col = self.column
        self._advance()  # Skip '
        value = []

        while self._current() and self._current() != "\n":
            value.append(self._advance())

        return Token(TokenType.COMMENT, "".join(value).strip(), start_line, start_col)

    def _read_label(self) -> Token:
        """Read a label (:label_name at start of statement)."""
        start_line = self.line
        start_col = self.column
        self._advance()  # Skip :
        value = []

        while self._current() and (self._current().isalnum() or self._current() == "_"):
            value.append(self._advance())

        if not value:
            # Just a colon, not a label
            return Token(TokenType.COLON, ":", start_line, start_col)

        return Token(TokenType.LABEL, "".join(value), start_line, start_col)

    def tokenize(self, include_comments: bool = False) -> Iterator[Token]:
        """
        Generate tokens from source.

        Args:
            include_comments: If True, yield COMMENT tokens. Default False (skip them).
        """
        while self.pos < len(self.source):
            self._skip_whitespace()

            # Check for line continuation
            if self._skip_line_continuation():
                continue

            char = self._current()
            start_line = self.line
            start_col = self.column

            if not char:
                break

            # Newline
            if char == "\n":
                self._advance()
                yield Token(TokenType.NEWLINE, "\\n", start_line, start_col)
                continue

            # Comment
            if char == "'":
                comment = self._read_comment()
                if include_comments:
                    yield comment
                continue

            # String
            if char in "\"'":
                # Single quote at start of line is comment, but inside expression it could be string
                # For now, treat ' as comment starter always
                if char == "'":
                    comment = self._read_comment()
                    if include_comments:
                        yield comment
                    continue
                yield self._read_string(char)
                continue

            # Double-quoted string
            if char == '"':
                yield self._read_string(char)
                continue

            # Number (including negative)
            if char.isdigit() or (char == "-" and self._peek().isdigit()):
                yield self._read_number()
                continue

            # Variable
            if char == "$":
                yield self._read_variable()
                continue

            # Label or colon
            if char == ":":
                yield self._read_label()
                continue

            # Identifier or keyword
            if char.isalpha() or char == "_":
                yield self._read_identifier_or_keyword()
                continue

            # Operators and delimiters
            if char == "+":
                self._advance()
                yield Token(TokenType.PLUS, "+", start_line, start_col)
            elif char == "-":
                self._advance()
                yield Token(TokenType.MINUS, "-", start_line, start_col)
            elif char == "*":
                self._advance()
                yield Token(TokenType.STAR, "*", start_line, start_col)
            elif char == "/":
                self._advance()
                yield Token(TokenType.SLASH, "/", start_line, start_col)
            elif char == "<":
                self._advance()
                if self._current() == "=":
                    self._advance()
                    yield Token(TokenType.LE, "<=", start_line, start_col)
                elif self._current() == ">":
                    self._advance()
                    yield Token(TokenType.NE, "<>", start_line, start_col)
                else:
                    yield Token(TokenType.LT, "<", start_line, start_col)
            elif char == ">":
                self._advance()
                if self._current() == "=":
                    self._advance()
                    yield Token(TokenType.GE, ">=", start_line, start_col)
                else:
                    yield Token(TokenType.GT, ">", start_line, start_col)
            elif char == "=":
                self._advance()
                if self._current() == "=":
                    self._advance()
                    yield Token(TokenType.EQEQ, "==", start_line, start_col)
                else:
                    yield Token(TokenType.EQ, "=", start_line, start_col)
            elif char == "!":
                self._advance()
                if self._current() == "=":
                    self._advance()
                    yield Token(TokenType.NE, "!=", start_line, start_col)
                else:
                    raise LexerError(f"Unexpected character: !", start_line, start_col)
            elif char == ".":
                self._advance()
                yield Token(TokenType.DOT, ".", start_line, start_col)
            elif char == "(":
                self._advance()
                yield Token(TokenType.LPAREN, "(", start_line, start_col)
            elif char == ")":
                self._advance()
                yield Token(TokenType.RPAREN, ")", start_line, start_col)
            elif char == "[":
                self._advance()
                yield Token(TokenType.LBRACKET, "[", start_line, start_col)
            elif char == "]":
                self._advance()
                yield Token(TokenType.RBRACKET, "]", start_line, start_col)
            elif char == ",":
                self._advance()
                yield Token(TokenType.COMMA, ",", start_line, start_col)
            elif char == "_":
                # Standalone underscore (not continuation)
                self._advance()
                yield Token(TokenType.UNDERSCORE, "_", start_line, start_col)
            else:
                raise LexerError(f"Unexpected character: {char!r}", start_line, start_col)

        yield Token(TokenType.EOF, "", self.line, self.column)
