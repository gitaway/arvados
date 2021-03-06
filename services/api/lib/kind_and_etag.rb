module KindAndEtag

  def self.included(base)
    base.extend(ClassMethods)
  end

  module ClassMethods
  end

  def kind
    'arvados#' + self.class.to_s.camelcase(:lower)
  end

  def etag
    Digest::MD5.hexdigest(self.inspect).to_i(16).to_s(36)
  end
end
