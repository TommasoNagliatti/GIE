require 'openstudio'
require 'json'
ROOT = File.expand_path('..', __dir__)
m = OpenStudio::Model::Model.new
m.getBuilding.setName('Escritorio ficticio Sao Paulo - 8000 m2 - sem VE')
m.getBuilding.setStandardsBuildingType('Office')
m.getTimestep.setNumberOfTimestepsPerHour(4)
m.getYearDescription.setCalendarYear(2026)
rp=m.getRunPeriod
rp.setBeginMonth(1); rp.setBeginDayOfMonth(1)
rp.setEndMonth(6); rp.setEndDayOfMonth(30)
rp.setUseWeatherFileHolidays(false); rp.setUseWeatherFileDaylightSavings(false)
sc=m.getSimulationControl
sc.setDoZoneSizingCalculation(true); sc.setDoSystemSizingCalculation(false); sc.setDoPlantSizingCalculation(false)
sc.setRunSimulationforSizingPeriods(false); sc.setRunSimulationforWeatherFileRunPeriods(true)
epw=Dir[File.join(ROOT,'clima','*.epw')].first
raise 'EPW ausente' unless epw
OpenStudio::Model::WeatherFile.setWeatherFile(m,OpenStudio::EpwFile.new(OpenStudio::Path.new(epw)))
site=m.getSite; site.setLatitude(-23.627); site.setLongitude(-46.655); site.setTimeZone(-3); site.setElevation(801.9)
ddy=Dir.chdir(File.join(ROOT,'clima')) { OpenStudio::EnergyPlus.loadAndTranslateIdf(OpenStudio::Path.new(Dir[File.join(ROOT,'clima','*.ddy')].first)).get }
selected=ddy.getDesignDays.select{|d| d.nameString.include?('Ann Htg 99.6% Condns DB') || d.nameString.include?('Ann Clg .4% Condns DB=>MWB')}
raise 'Dias de projeto nao encontrados' unless selected.size==2
selected.each{|d| d.clone(m)}

def opaque(m,name,layers)
  c=OpenStudio::Model::Construction.new(m); c.setName(name)
  materials={}
  layers.each_with_index do |(th,k,rho,cp),i|
    if materials[[th,k,rho,cp]]
      c.insertLayer(i,materials[[th,k,rho,cp]])
      next
    end
    mat=OpenStudio::Model::StandardOpaqueMaterial.new(m)
    mat.setName("#{name} camada #{i}"); mat.setThickness(th); mat.setConductivity(k)
    mat.setDensity(rho); mat.setSpecificHeat(cp); c.insertLayer(i,mat); materials[[th,k,rho,cp]]=mat
  end
  c
end
wall=opaque(m,'Alvenaria rebocada',[[0.02,1.0,1800,840],[0.15,0.6,1200,840],[0.02,1.0,1800,840]])
roof=opaque(m,'Cobertura isolada',[[0.10,1.7,2300,880],[0.05,0.04,30,1400],[0.02,0.16,800,1090]])
slab=opaque(m,'Laje concreto',[[0.15,1.7,2300,880]])
glass=OpenStudio::Model::SimpleGlazing.new(m); glass.setUFactor(3.0); glass.setSolarHeatGainCoefficient(0.40); glass.setVisibleTransmittance(0.6)
win=OpenStudio::Model::Construction.new(m); win.setName('Vidro U3 SHGC0.4'); win.insertLayer(0,glass)

def schedule(m,name,weekday,saturday,sunday)
  s=OpenStudio::Model::ScheduleRuleset.new(m); s.setName(name)
  [[s.defaultDaySchedule,weekday],[s.summerDesignDaySchedule,weekday],[s.winterDesignDaySchedule,weekday]].each do |d,values|
    values.each{|hour,value| d.addValue(OpenStudio::Time.new(0,hour,0,0),value)}
  end
  [[saturday,:setApplySaturday],[sunday,:setApplySunday]].each do |values,method|
    rule=OpenStudio::Model::ScheduleRule.new(s); rule.send(method,true)
    values.each{|hour,value| rule.daySchedule.addValue(OpenStudio::Time.new(0,hour,0,0),value)}
  end
  s
end
occ=schedule(m,'Ocupacao',[[7,0],[8,0.2],[9,0.65],[12,0.95],[13,0.55],[17,0.9],[19,0.5],[21,0.2],[22,0.08],[24,0]],[[8,0],[9,0.1],[13,0.25],[16,0.12],[22,0.03],[24,0]],[[9,0],[15,0.03],[24,0]])
lights=schedule(m,'Iluminacao',[[7,0.05],[8,0.3],[9,0.7],[12,0.95],[13,0.75],[18,0.95],[20,0.65],[22,0.3],[24,0.05]],[[8,0.05],[9,0.15],[13,0.35],[16,0.2],[22,0.1],[24,0.05]],[[9,0.05],[15,0.1],[24,0.05]])
plugs=schedule(m,'Computadores e demais equipamentos',[[7,0.2],[8,0.35],[9,0.7],[12,0.95],[13,0.65],[17,0.9],[19,0.6],[22,0.3],[24,0.2]],[[8,0.2],[13,0.35],[17,0.25],[24,0.2]],[[24,0.2]])
hvac=schedule(m,'HVAC 07-22',[[7,0],[22,1],[24,0]],[[8,0],[16,1],[24,0]],[[24,0]])
cool=schedule(m,'Resfriamento 24C',[[7,30],[22,24],[24,30]],[[8,30],[16,24],[24,30]],[[24,30]])
heat=schedule(m,'Aquecimento 20C',[[7,15],[22,20],[24,15]],[[8,15],[16,20],[24,15]],[[24,15]])
activity=OpenStudio::Model::ScheduleConstant.new(m); activity.setName('Atividade sedentaria 120 W pessoa'); activity.setValue(120)
pd=OpenStudio::Model::PeopleDefinition.new(m); pd.setPeopleperSpaceFloorArea(0.08)
ld=OpenStudio::Model::LightsDefinition.new(m); ld.setWattsperSpaceFloorArea(8)
ed=OpenStudio::Model::ElectricEquipmentDefinition.new(m); ed.setWattsperSpaceFloorArea(12)
spaces=OpenStudio::Model::SpaceVector.new
4.times do |floor|
  2.times do |ix|
    2.times do |iy|
      x=ix*25.0; y=iy*20.0; z=floor*3.5
      pts=OpenStudio::Point3dVector.new
      [[x,y,z],[x,y+20,z],[x+25,y+20,z],[x+25,y,z]].each{|p| pts << OpenStudio::Point3d.new(*p)}
      s=OpenStudio::Model::Space.fromFloorPrint(pts,3.5,m).get; s.setName("P#{floor+1}_#{ix}_#{iy}"); spaces << s
      zone=OpenStudio::Model::ThermalZone.new(m); zone.setName("Zona #{s.nameString}"); s.setThermalZone(zone)
      p=OpenStudio::Model::People.new(pd); p.setSpace(s); p.setNumberofPeopleSchedule(occ); p.setActivityLevelSchedule(activity)
      l=OpenStudio::Model::Lights.new(ld); l.setSpace(s); l.setSchedule(lights)
      e=OpenStudio::Model::ElectricEquipment.new(ed); e.setSpace(s); e.setSchedule(plugs); e.setEndUseSubcategory('Computadores e cargas de escritorio')
      inf=OpenStudio::Model::SpaceInfiltrationDesignFlowRate.new(m); inf.setSpace(s); inf.setAirChangesperHour(0.15); inf.setSchedule(m.alwaysOnDiscreteSchedule)
      oa=OpenStudio::Model::DesignSpecificationOutdoorAir.new(m); oa.setOutdoorAirMethod('Sum'); oa.setOutdoorAirFlowperPerson(0.0075); oa.setOutdoorAirFlowperFloorArea(0.0003); s.setDesignSpecificationOutdoorAir(oa)
      thermostat=OpenStudio::Model::ThermostatSetpointDualSetpoint.new(m); thermostat.setCoolingSetpointTemperatureSchedule(cool); thermostat.setHeatingSetpointTemperatureSchedule(heat); zone.setThermostatSetpointDualSetpoint(thermostat)
      fan=OpenStudio::Model::FanConstantVolume.new(m); fan.setPressureRise(350); fan.setFanEfficiency(0.6)
      heating=OpenStudio::Model::CoilHeatingElectric.new(m)
      cooling=OpenStudio::Model::CoilCoolingDXSingleSpeed.new(m); cooling.setRatedCOP(3.2)
      unit=OpenStudio::Model::ZoneHVACPackagedTerminalAirConditioner.new(m,hvac,fan,heating,cooling)
      unit.setName("Ar condicionado #{s.nameString}"); unit.setSupplyAirFanOperatingModeSchedule(m.alwaysOnDiscreteSchedule)
      unit.setOutdoorAirFlowRateDuringCoolingOperation(0.45); unit.setOutdoorAirFlowRateDuringHeatingOperation(0.45); unit.setOutdoorAirFlowRateWhenNoCoolingorHeatingisNeeded(0.45)
      unit.addToThermalZone(zone)
    end
  end
end
OpenStudio::Model.matchSurfaces(spaces)
m.getSurfaces.each do |s|
  s.setConstruction(s.surfaceType=='Wall' ? wall : (s.surfaceType=='RoofCeiling' && s.outsideBoundaryCondition=='Outdoors' ? roof : slab))
  if s.surfaceType=='Wall' && s.outsideBoundaryCondition=='Outdoors'
    w=s.setWindowToWallRatio(0.30); w.get.setConstruction(win) if w.is_initialized
  end
end
# Monthly ground boundary assumption, not measured site soil temperatures.
ground=m.getSiteGroundTemperatureBuildingSurface
%w[January February March April May June July August September October November December].zip([23,24,24,22,20,18,17,18,19,20,21,22]).each{|month,t| ground.send("set#{month}GroundTemperature",t)}
['Electricity:Facility','Cooling:Electricity','Heating:Electricity','Fans:Electricity','InteriorLights:Electricity','InteriorEquipment:Electricity'].each do |name|
  out=OpenStudio::Model::OutputMeter.new(m); out.setName(name); out.setReportingFrequency('Timestep')
end
['Site Outdoor Air Drybulb Temperature','Site Outdoor Air Relative Humidity','Facility Total Electricity Demand Rate','Zone Mean Air Temperature','Zone Thermostat Cooling Setpoint Temperature','Zone Thermostat Heating Setpoint Temperature'].each do |name|
  out=OpenStudio::Model::OutputVariable.new(name,m); out.setReportingFrequency('Timestep')
end
m.getOutputControlFiles.setOutputCSV(true)
m.getOutputSQLite.setOptionType('SimpleAndTabular')
raise "Area incorreta #{m.getBuilding.floorArea}" unless (m.getBuilding.floorArea-8000).abs<0.01
m.save(OpenStudio::Path.new(File.join(ROOT,'modelo','predio_sp.osm')),true)
ft=OpenStudio::EnergyPlus::ForwardTranslator.new
idf=ft.translateModel(m)
raise ft.errors.map(&:logMessage).join("\n") unless ft.errors.empty?
idf.objects.select{|o| o.iddObject.name.start_with?('LifeCycleCost:')}.each(&:remove)
idf.save(OpenStudio::Path.new(File.join(ROOT,'modelo','predio_sp.idf')),true)
rp.setEndMonth(1); rp.setEndDayOfMonth(7)
test_idf=ft.translateModel(m)
test_idf.objects.select{|o| o.iddObject.name.start_with?('LifeCycleCost:')}.each(&:remove)
test_idf.save(OpenStudio::Path.new(File.join(ROOT,'modelo','predio_sp_teste.idf')),true)
puts JSON.pretty_generate({area_m2:m.getBuilding.floorArea,zonas:m.getThermalZones.size,janelas:m.getSubSurfaces.size,dias_projeto:selected.map(&:nameString),avisos:ft.warnings.map(&:logMessage)})
