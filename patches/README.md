# Dependency patches

The versioned Abseil/protobuf patches originate from Google OR-Tools at
`551ad10d94835c99e5e1e684500d3db398c0e345` (`patches/`).
The namespace patch gives every SDK consumer the same private Abseil identity.
All patches are included in the source/recipe identity and applied to private
producer checkouts, never to a consumer or a shared developer checkout.
