from enum import Enum, auto

# ============================================================
# TokenKind: Token types for Mryl language (Rust-style)
# ============================================================
class TokenKind(Enum):
    # Symbols and Operators
    PLUS = auto()        # +
    MINUS = auto()       # -
    PLUS_PLUS = auto()    # ++
    MINUS_MINUS = auto()  # --
    STAR = auto()        # *
    SLASH = auto()       # /
    MOD = auto()         # %
    EQ = auto()          # =
    EQ_EQ = auto()       # ==
    BANG_EQ = auto()     # !=
    LT = auto()          # <
    GT = auto()          # >
    LT_EQ = auto()       # <=
    GT_EQ = auto()       # >=
    ARROW = auto()       # ->
    FAT_ARROW = auto()   # =>

    # Async/Await
    ASYNC = auto()
    AWAIT = auto()
    WEAK  = auto()   # weak — WeakTask 取得
    
    # Compound assignment operators
    PLUS_EQ = auto()     # +=
    MINUS_EQ = auto()    # -=
    STAR_EQ = auto()     # *=
    SLASH_EQ = auto()    # /=
    MOD_EQ = auto()      # %=
    
    # Logical operators
    AND = auto()         # &&
    OR = auto()          # ||
    NOT = auto()         # !
    
    # Bitwise operators
    AMPERSAND = auto()   # &
    PIPE = auto()        # |
    CARET = auto()       # ^
    TILDE = auto()       # ~
    LSHIFT = auto()      # <<
    RSHIFT = auto()      # >>
    LSHIFT_EQ = auto()   # <<=
    RSHIFT_EQ = auto()   # >>=
    CARET_EQ = auto()    # ^=

    LPAREN = auto()      # (
    RPAREN = auto()      # )
    LBRACE = auto()      # {
    RBRACE = auto()      # }
    LBRACKET = auto()    # [
    RBRACKET = auto()    # ]
    COMMA = auto()       # ,
    SEMICOLON = auto()   # ;
    COLON = auto()       # :
    DOT = auto()         # .

    # Literals
    IDENT = auto()
    NUMBER = auto()
    STRING = auto()

    # Keywords
    FN = auto()
    LET = auto()
    FIX = auto()
    CONST = auto()
    STRUCT = auto()
    IMPL = auto()
    RETURN = auto()
    IF = auto()
    ELSE = auto()
    WHILE = auto()
    FOR = auto()
    BREAK = auto()
    CONTINUE = auto()
    IN = auto()
    TRUE = auto()
    FALSE = auto()

    # Preprocessor directives (for conditional compilation)
    HASH_IFDEF = auto()   # #ifdef
    HASH_IFNDEF = auto()  # #ifndef
    HASH_IF = auto()      # #if
    HASH_ENDIF = auto()   # #endif
    HASH_ELSE = auto()    # #else
    HASH = auto()         # #

    # Types
    INT = auto()
    BOOL = auto()
    STRING_TYPE = auto()
    VOID = auto()

    # Range Operators
    DOTDOT = auto()      # ..

    # Enum / path separator
    ENUM = auto()        # enum keyword
    MATCH = auto()       # match keyword (reserved for future use)
    DOUBLE_COLON = auto()  # ::

    # Static
    STATIC = auto()      # static keyword

    # Inclusive range keyword
    TO = auto()          # to keyword

    EOF = auto()

class Token:
    def __init__(self, kind, value, line, column):
        self.kind = kind
        self.value = value
        self.line = line
        self.column = column

    def __repr__(self):
        return f"{self.kind.name}({self.value!r}) at {self.line}:{self.column}" 

class Lexer:
    KEYWORDS = {
        "fn": TokenKind.FN,
        "let": TokenKind.LET,
        "fix": TokenKind.FIX,
        "const": TokenKind.CONST,
        "struct": TokenKind.STRUCT,
        "impl": TokenKind.IMPL,
        "return": TokenKind.RETURN,
        "if": TokenKind.IF,
        "else": TokenKind.ELSE,
        "while": TokenKind.WHILE,
        "for": TokenKind.FOR,
        "break": TokenKind.BREAK,
        "continue": TokenKind.CONTINUE,
        "in": TokenKind.IN,
        "true": TokenKind.TRUE,
        "false": TokenKind.FALSE,
        "async": TokenKind.ASYNC,
        "await": TokenKind.AWAIT,
        "weak":  TokenKind.WEAK,
        "enum":  TokenKind.ENUM,
        "match": TokenKind.MATCH,
        "static": TokenKind.STATIC,
        "to": TokenKind.TO,
    }

    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.column = 1
        self.current_char = self.source[self.pos] if self.source else None

    # ----------------------------
    # Basic operations
    # ----------------------------
    def advance(self):
        if self.current_char == '\n':
            self.line += 1
            self.column = 1
        else:
            self.column += 1

        self.pos += 1
        if self.pos >= len(self.source):
            self.current_char = None
        else:
            self.current_char = self.source[self.pos]

    def peek(self):
        next = self.pos + 1
        if next >= len(self.source):
            return None
        return self.source[next]
    
    def peek_ahead(self, n):
        """Peek n characters ahead"""
        next_pos = self.pos + n
        if next_pos >= len(self.source):
            return None
        return self.source[next_pos]

    # ----------------------------
    # Comment handling (Rust-style)
    # ----------------------------
    def skip_comment(self):
        # Handle // line comments
        if self.current_char == '/' and self.peek() == '/':
            while self.current_char not in ('\n', None):
                self.advance()
            return True

        # Handle /* block comments */
        if self.current_char == '/' and self.peek() == '*':
            self.advance()  # /
            self.advance()  # *
            while True:
                if self.current_char is None:
                    raise SyntaxError("Unterminated block comment")
                if self.current_char == '*' and self.peek() == '/':
                    self.advance()
                    self.advance()
                    break
                self.advance()
            return True

        return False

    def read_token(self):
        """Read and return next token"""
        while self.current_char is not None and (
            self.current_char.isspace() or self.current_char == '\u3000'
        ):
            self.advance()

        if self.skip_comment():
            return self.read_token()

        if self.current_char is None:
            return Token(TokenKind.EOF, "", self.line, self.column)

        ch = self.current_char
        line, col = self.line, self.column

        # Preprocessor directives (for conditional compilation)
        if ch == '#':
            self.advance()
            # Read the directive keyword
            if self.current_char and (self.current_char.isalpha() or self.current_char == '_'):
                directive = self.read_identifier()
                if directive == "ifdef":
                    return Token(TokenKind.HASH_IFDEF, "#ifdef", line, col)
                elif directive == "ifndef":
                    return Token(TokenKind.HASH_IFNDEF, "#ifndef", line, col)
                elif directive == "if":
                    return Token(TokenKind.HASH_IF, "#if", line, col)
                elif directive == "endif":
                    return Token(TokenKind.HASH_ENDIF, "#endif", line, col)
                elif directive == "else":
                    return Token(TokenKind.HASH_ELSE, "#else", line, col)
                else:
                    raise SyntaxError(f"Unknown preprocessor directive: #{directive}")
            else:
                return Token(TokenKind.HASH, "#", line, col)

        # Identifier / Keywords
        if ch.isalpha() or ch == '_':
            ident = self.read_identifier()
            kind = self.KEYWORDS.get(ident, TokenKind.IDENT)
            return Token(kind, ident, line, col)

        if ch.isdigit():
            num = self.read_number()
            return Token(TokenKind.NUMBER, num, line, col)

        if ch == '"':
            s = self.read_string()
            return Token(TokenKind.STRING, s, line, col)

        # 3-character operators
        if ch == '<' and self.peek() == '<' and self.peek_ahead(2) == '=':
            self.advance(); self.advance(); self.advance()
            return Token(TokenKind.LSHIFT_EQ, "<<=", line, col)
        if ch == '>' and self.peek() == '>' and self.peek_ahead(2) == '=':
            self.advance(); self.advance(); self.advance()
            return Token(TokenKind.RSHIFT_EQ, ">>=" , line, col)
        
        # 2-character operators
        if ch == '=' and self.peek() == '=':
            self.advance(); self.advance()
            return Token(TokenKind.EQ_EQ, "==", line, col)
        if ch == '!' and self.peek() == '=':
            self.advance(); self.advance()
            return Token(TokenKind.BANG_EQ, "!=", line, col)
        if ch == '<' and self.peek() == '=':
            self.advance(); self.advance()
            return Token(TokenKind.LT_EQ, "<=", line, col)
        if ch == '>' and self.peek() == '=':
            self.advance(); self.advance()
            return Token(TokenKind.GT_EQ, ">=", line, col)
        if ch == '+' and self.peek() == '+':
            self.advance(); self.advance()
            return Token(TokenKind.PLUS_PLUS, "++", line, col)
        if ch == '-' and self.peek() == '-':
            self.advance(); self.advance()
            return Token(TokenKind.MINUS_MINUS, "--", line, col)
        if ch == '-' and self.peek() == '>':
            self.advance(); self.advance()
            return Token(TokenKind.ARROW, "->", line, col)
        if ch == '=' and self.peek() == '>':
            self.advance(); self.advance()
            return Token(TokenKind.FAT_ARROW, "=>", line, col)
        if ch == '.' and self.peek() == '.':
            self.advance(); self.advance()
            return Token(TokenKind.DOTDOT, "..", line, col)
        if ch == '+' and self.peek() == '=':
            self.advance(); self.advance()
            return Token(TokenKind.PLUS_EQ, "+=", line, col)
        if ch == '-' and self.peek() == '=':
            self.advance(); self.advance()
            return Token(TokenKind.MINUS_EQ, "-=", line, col)
        if ch == '*' and self.peek() == '=':
            self.advance(); self.advance()
            return Token(TokenKind.STAR_EQ, "*=", line, col)
        if ch == '/' and self.peek() == '=':
            self.advance(); self.advance()
            return Token(TokenKind.SLASH_EQ, "/=", line, col)
        if ch == '%' and self.peek() == '=':
            self.advance(); self.advance()
            return Token(TokenKind.MOD_EQ, "%=", line, col)
        if ch == '&' and self.peek() == '&':
            self.advance(); self.advance()
            return Token(TokenKind.AND, "&&", line, col)
        if ch == '|' and self.peek() == '|':
            self.advance(); self.advance()
            return Token(TokenKind.OR, "||", line, col)
        if ch == '<' and self.peek() == '<':
            self.advance(); self.advance()
            return Token(TokenKind.LSHIFT, "<<", line, col)
        if ch == '>' and self.peek() == '>':
            self.advance(); self.advance()
            return Token(TokenKind.RSHIFT, ">>", line, col)
        if ch == '^' and self.peek() == '=':
            self.advance(); self.advance()
            return Token(TokenKind.CARET_EQ, "^=", line, col)
        # :: (double colon — must be before single :)
        if ch == ':' and self.peek() == ':':
            self.advance(); self.advance()
            return Token(TokenKind.DOUBLE_COLON, "::", line, col)

        single_map = {
            '+': TokenKind.PLUS,
            '-': TokenKind.MINUS,
            '*': TokenKind.STAR,
            '/': TokenKind.SLASH,
            '%': TokenKind.MOD,
            '=': TokenKind.EQ,
            '<': TokenKind.LT,
            '>': TokenKind.GT,
            '!': TokenKind.NOT,
            '&': TokenKind.AMPERSAND,
            '|': TokenKind.PIPE,
            '^': TokenKind.CARET,
            '~': TokenKind.TILDE,
            '(': TokenKind.LPAREN,
            ')': TokenKind.RPAREN,
            '{': TokenKind.LBRACE,
            '}': TokenKind.RBRACE,
            '[': TokenKind.LBRACKET,
            ']': TokenKind.RBRACKET,
            ',': TokenKind.COMMA,
            ';': TokenKind.SEMICOLON,
            ':': TokenKind.COLON,
            '.': TokenKind.DOT
        }

        if ch in single_map:
            self.advance()
            kind = single_map[ch]
            value = ch
            return Token(kind, value, line, col)

        raise SyntaxError(f"Unexpected character {ch!r} at {line}:{col}")

    # ----------------------------
    # Helper methods: token components
    # ----------------------------
    def read_identifier(self):
        """Read identifier or keyword"""
        start = self.pos
        while self.current_char is not None and (self.current_char.isalnum() or self.current_char == '_'):
            self.advance()
        return self.source[start:self.pos]

    def read_number(self):
        """Read numeric literal with optional type specification"""
        # Integer part (digits and underscore separators)
        start = self.pos
        while self.current_char is not None and (self.current_char.isdigit() or self.current_char == '_'):
            self.advance()
        
        # Optional decimal part
        if self.current_char == '.' and self.peek() is not None and self.peek().isdigit():
            self.advance()  # .
            while self.current_char is not None and self.current_char.isdigit():
                self.advance()
        
        # Type specification: (type) e.g., 5(u8), 3.14(f64)
        if self.current_char == '(':
            self.advance()  # (
            # Read type name (i8, u32, f64, etc.)
            while self.current_char is not None and (self.current_char.isalnum() or self.current_char == '_'):
                self.advance()
            if self.current_char == ')':
                self.advance()  # )
        # Legacy suffix style: 5u8, 3.14f64, etc. (compatibility)
        elif self.current_char is not None and self.current_char.isalpha():
            self.advance()  # First character (i, u, f)
            while self.current_char is not None and self.current_char.isdigit():
                self.advance()  # Digits (8, 16, 32, 64)
        
        return self.source[start:self.pos]

    def read_string(self):
        """Read string literal with escape sequences"""
        self.advance()  # opening quote
        value_chars = []
        while self.current_char is not None and self.current_char != '"':
            if self.current_char == '\\':
                self.advance()
                if self.current_char == 'n':
                    value_chars.append('\n')
                elif self.current_char == 't':
                    value_chars.append('\t')
                elif self.current_char == 'r':
                    value_chars.append('\r')
                elif self.current_char == '"':
                    value_chars.append('"')
                elif self.current_char == '\\':
                    value_chars.append('\\')
                else:
                    value_chars.append(self.current_char)
                self.advance()
            else:
                value_chars.append(self.current_char)
                self.advance()

        if self.current_char != '"':
            raise SyntaxError(f"Unterminated string at {self.line}:{self.column}")

        self.advance()  # closing quote
        return "".join(value_chars)