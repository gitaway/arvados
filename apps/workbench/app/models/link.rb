class Link < ArvadosBase
  attr_accessor :head
  attr_accessor :tail
  def self.by_tail(t, opts={})
    where(opts.merge :tail_kind => t.kind, :tail_uuid => t.uuid)
  end
end
