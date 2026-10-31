### Historical decisions related to this change

**[Accepted] Type Parameter Syntax** (`DEC-068ac3e89c`, relevance 0.7)
- why surfaced: semantically similar to PR text (0.33)
- reason: Doesn’t prevent leveraging existing mechanisms ([source](https://discuss.python.org/t/pep-695-type-parameter-syntax/21646/24))
- reason: Provides flexibility for exploring extensions to the type system. ([source](https://discuss.python.org/t/pep-695-type-parameter-syntax/21646/24))
- evidence: [erictraut](https://discuss.python.org/t/pep-695-type-parameter-syntax/21646/1): "It proposes to add an improved syntax for specifying type parameters within a generic class, function, or type alias."

**[REJECTED earlier] Variance is relevant to the question of understanding the type variable T** (`DEC-d768cd4ed8`, relevance 0.5)
- why surfaced: semantically similar to PR text (0.26)
- evidence: [oscarbenjamin](https://discuss.python.org/t/pep-695-type-parameter-syntax/21646/66): "Oh, I missed that it is in the PEP:  type ListOrSet[T] = list[T] | set[T]
This does introduce the type variable T so that the TypeVar is not needed."

**[Accepted] Explicit Type Declarations** (`DEC-1786668d00`, relevance 0.5)
- why surfaced: semantically similar to PR text (0.26)
- reason: Offers a more intuitive and familiar syntax for developers coming from other languages. ([source](https://discuss.python.org/t/pep-695-type-parameter-syntax/21646/19))
- evidence: [erictraut](https://discuss.python.org/t/pep-695-type-parameter-syntax/21646/19): "And finally, a decorator-based syntax would look significantly different than any other language that we surveyed in the appendix of the PEP."

