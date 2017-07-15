# XXX Make compatible with Python 2.
# XXX Make sure states can be transferred across Python versions (including
#     pickled states); how do we deal with the str / bytes mismatch?
# XXX fromstate constructor method? Or function, so that it can select
#     the appropriate class to use.
# XXX References: O'Neill, L'Ecuyer, Knuth MMIX.
# XXX Think harder about reproducibility; document it.

import operator as _operator
import os as _os
import random as _random

_UINT32_MASK = 2**32 - 1
_UINT64_MASK = 2**64 - 1

# Constants reportedly used by Knuth for MMIX's LCG.  These values are given on
# the Wikipedia page for Linear Congruential Generators, and can be found in
# various other references online, but I was unable to find the primary source.
_KNUTH_MMIX_LCG_MULTIPLIER = 6364136223846793005
_KNUTH_MMIX_LCG_INCREMENT = 1442695040888963407


def _rotate32(v, r):
    """
    An unsigned 32-bit bitwise 'clockwise' rotation of r bits on v.

    If v has more than 32 bits, only the least significant 32 bits
    are used.

    Parameters
    ----------
    v : integer in range 0 <= v < 2**32
        The value to rotate.
    r : integer in the range 0 <= r < 32
        The number of bits to rotate by.

    Returns
    -------
    integer in range 0 <= v < 2**32
        Result of shifting v right by r places, rotating the
        bits that drop off back into the high end of v.
    """
    return (v >> r | v << (32-r)) & _UINT32_MASK


class PCG_XSH_RR_V0(_random.Random):
    """
    Random subclass based on Melissa O'Neill's PCG family.

    This implements the generator described in section 6.3.1 of the PCG paper,
    PCG-XSH-RR, sitting on a 64-bit LCG from Knuth.
    """

    VERSION = 'pcgrand.PCG_XSH_RR_V0'

    def __init__(self, seed=None, sequence=0):
        multiplier = _KNUTH_MMIX_LCG_MULTIPLIER
        sequence = _operator.index(sequence) & _UINT64_MASK
        increment = (2 * sequence + _KNUTH_MMIX_LCG_INCREMENT) & _UINT64_MASK

        self._multiplier = multiplier
        self._increment = increment
        super(PCG_XSH_RR_V0, self).__init__(seed)

    def seed(self, seed=None):
        """Initialize internal state from hashable object.
        """
        # XXX Compatibility note: unlike the base Random generator, we don't
        # permit seeding from an arbitrary hashable object, since that makes it
        # harder to guarantee reproducibility in the case that the hash
        # changes.  See also http://bugs.python.org/issue27706.
        if seed is None:
            seed = int.from_bytes(_os.urandom(8), byteorder='little')
        else:
            seed = _operator.index(seed)

        self._set_state_from_seed(seed)

    def random(self):
        """Get the next random number in the range [0.0, 1.0)."""

        # Same generation method as in the Mersenne Twister code. Constants in
        # the final line are 2**26 and 2**53.
        a = self._next_word() >> 5
        b = self._next_word() >> 6
        return (a*67108864.0+b)/9007199254740992.0

    def _randbelow(self, n):
        """Return a random integer in range(n)."""
        # Invariant: x is uniformly distributed in range(h).
        x, h = 0, 1
        while True:
            q, r = divmod(h, n)
            if r <= x:
                return (x - r) // q
            x, h = x << 32 | self._next_word(), r << 32

    def getstate(self):
        """Return internal state; can be passed to setstate() later."""
        parameters = self._multiplier, self._increment
        return self.VERSION, parameters, self._state, self.gauss_next

    def setstate(self, state):
        """Restore internal state from object returned by getstate()."""
        version = state[0]

        if version == self.VERSION:
            parameters, state, gauss_next = state[1:]
            self.gauss_next = gauss_next
            self._state = state
            self._multiplier, self._increment = parameters
        else:
            raise ValueError(
                "state with version %r passed to "
                "setstate() of version %r" %
                (version, self.VERSION)
            )

    def getrandbits(self, k):
        """Generate an integer in the range [0, 2**k).

        Parameters
        ----------
        k : nonnegative integer

        """
        # XXX Compatibility note: k=0 is accepted.

        k = _operator.index(k)
        if k < 0:
            raise ValueError("Number of bits should be nonnegative.")

        # k = 32 * numwords - excess_bits, 0 <= excess_bits < 32
        numwords, excess_bits = -(-k // 32), -k % 32
        acc = 0
        for _ in range(numwords):
            acc = acc << 32 | self._next_word()
        return acc >> excess_bits

    def jumpahead(self, n):
        """Jump ahead or back in the sequence of random numbers."""

        # Sequence has period 2**64-1, so we can reduce modulo 2**64.
        n &= _UINT64_MASK
        a, c = self._multiplier, self._increment

        # Left-to-right algorithm.
        an, cn = 1, 0
        for bit in format(n, 'b'):
            an, cn = an * an & _UINT64_MASK, an * cn + cn & _UINT64_MASK
            if bit == '1':
                an, cn = a * an & _UINT64_MASK, a * cn + c & _UINT64_MASK

        self._state = (self._state * an + cn) & _UINT64_MASK

    # Private helper functions.

    def _set_state_from_seed(self, seed):
        """Initialize generator from a given seed.

        Parameters
        ----------
        seed : int
            An integer seed to use to prime the generator.
        """
        seed &= _UINT64_MASK

        self._state = 0
        self._next_word()
        self._state = (self._state + seed) & _UINT64_MASK
        self._next_word()

    def _next_word(self):
        """Return next output; advance the underlying LCG.
        """
        state = self._state
        output_word = ((state ^ (state >> 18)) >> 27) & _UINT32_MASK
        output_shift = state >> 59
        output = _rotate32(output_word, output_shift)
        new_state = state * self._multiplier + self._increment
        new_state &= _UINT64_MASK
        self._state = new_state
        return output
