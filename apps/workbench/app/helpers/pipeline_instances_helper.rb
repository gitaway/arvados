module PipelineInstancesHelper
  def pipeline_summary object=nil
    object ||= @object
    ret = {todo:0, running:0, queued:0, done:0, failed:0, total:0}
    object.components.values.each do |c|
      ret[:total] += 1
      case
      when !c[:job]
        ret[:todo] += 1
      when c[:job][:success]
        ret[:done] += 1
      when c[:job][:failed]
        ret[:failed] += 1
      when c[:job][:finished_at]
        ret[:running] += 1      # XXX finished but !success and !failed??
      when c[:job][:started_at]
        ret[:running] += 1
      else
        ret[:queued] += 1
      end
    end
    ret.merge! Hash[ret.collect do |k,v|
                      [('percent_' + k.to_s).to_sym,
                       ret[:total]<1 ? 0 : (100.0*v/ret[:total]).floor]
                    end]
    ret
  end

  def pipeline_jobs object=nil
    object ||= @object
    if object.components[:steps].is_a? Array
      pipeline_jobs_oldschool object
    elsif object.components.is_a? Hash
      pipeline_jobs_newschool object
    end
  end

  def render_pipeline_jobs
    pipeline_jobs.collect do |pj|
      render_pipeline_job pj
    end
  end

  def render_pipeline_job pj
    if pj[:percent_done]
      pj[:progress_bar] = raw("<div class=\"progress\" style=\"width:100px\"><span class=\"progress-bar progress-bar-success\" style=\"width:#{pj[:percent_done]}%\"></span><span class=\"progress-bar\" style=\"width:#{pj[:percent_running]}%\"></span></div>")
    elsif pj[:progress]
      raw("<div class=\"progress\" style=\"width:100px\"><span class=\"progress-bar\" style=\"width:#{pj[:progress]*100}%\"></span></div>")
    end
    pj[:output_link] = link_to_if_arvados_object pj[:output]
    pj[:job_link] = link_to_if_arvados_object pj[:job][:uuid]
    pj
  end

  protected

  def pipeline_jobs_newschool object
    ret = []
    i = -1
    object.components.each do |cname, c|
      i += 1
      pj = {index: i, name: cname}
      pj[:job] = c[:job].is_a?(Hash) ? c[:job] : {}
      pj[:percent_done] = 0
      pj[:percent_running] = 0
      if pj[:job][:success]
        if pj[:job][:output]
          pj[:progress] = 1.0
          pj[:percent_done] = 100
        else
          pj[:progress] = 0.0
        end
      else
        if pj[:job][:tasks_summary]
          begin
            ts = pj[:job][:tasks_summary]
            denom = ts[:done].to_f + ts[:running].to_f + ts[:todo].to_f
            pj[:progress] = (ts[:done].to_f + ts[:running].to_f/2) / denom
            pj[:percent_done] = 100.0 * ts[:done].to_f / denom
            pj[:percent_running] = 100.0 * ts[:running].to_f / denom
            pj[:progress_detail] = "#{ts[:done]} done #{ts[:running]} run #{ts[:todo]} todo"
          rescue
            pj[:progress] = 0.5
            pj[:percent_done] = 0.0
            pj[:percent_running] = 100.0
          end
        else
          pj[:progress] = 0.0
        end
      end
      if pj[:job][:success]
        pj[:result] = 'complete'
        pj[:complete] = true
        pj[:progress] = 1.0
      elsif pj[:job][:finished_at]
        pj[:result] = 'failed'
        pj[:failed] = true
      elsif pj[:job][:started_at]
        pj[:result] = 'running'
      elsif pj[:job][:uuid]
        pj[:result] = 'queued'
      else
        pj[:result] = 'none'
      end
      pj[:job_id] = pj[:job][:uuid]
      pj[:script] = pj[:job][:script] || c[:script]
      pj[:script_parameters] = pj[:job][:script_parameters] || c[:script_parameters]
      pj[:script_version] = pj[:job][:script_version] || c[:script_version]
      pj[:output] = pj[:job][:output]
      pj[:finished_at] = (Time.parse(pj[:job][:finished_at]) rescue nil)
      ret << pj
    end
    ret
  end

  def pipeline_jobs_oldschool object
    ret = []
    object.components[:steps].each_with_index do |step, i|
      pj = {index: i, name: step[:name]}
      if step[:complete] and step[:complete] != 0
        if step[:output_data_locator]
          pj[:progress] = 1.0
        else
          pj[:progress] = 0.0
        end
      else
        if step[:progress] and
            (re = step[:progress].match /^(\d+)\+(\d+)\/(\d+)$/)
          pj[:progress] = (((re[1].to_f + re[2].to_f/2) / re[3].to_f) rescue 0.5)
        else
          pj[:progress] = 0.0
        end
        if step[:failed]
          pj[:result] = 'failed'
          pj[:failed] = true
        end
      end
      if step[:warehousejob]
        if step[:complete]
          pj[:result] = 'complete'
          pj[:complete] = true
          pj[:progress] = 1.0
        elsif step[:warehousejob][:finishtime]
          pj[:result] = 'failed'
          pj[:failed] = true
        elsif step[:warehousejob][:starttime]
          pj[:result] = 'running'
        else
          pj[:result] = 'queued'
        end
      end
      pj[:progress_detail] = (step[:progress] rescue nil)
      pj[:job_id] = (step[:warehousejob][:id] rescue nil)
      pj[:job_link] = pj[:job_id]
      pj[:script] = step[:function]
      pj[:script_version] = (step[:warehousejob][:revision] rescue nil)
      pj[:output] = step[:output_data_locator]
      pj[:finished_at] = (Time.parse(step[:warehousejob][:finishtime]) rescue nil)
      ret << pj
    end
    ret
  end
end
