# -*- coding: utf-8 -*-

##############################################################################
#
#    OpenCivil module for OpenERP, module Etat-Civil
#    Copyright (C) 200X Company (<http://website>) pyf
#
#    This file is a part of penCivil
#
#    penCivil is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, ors_user
#    (at your option) any later version.
#
#    penCivil is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################


from openbase.openbase_core import OpenbaseCore

import time
import operator
import logging
import pytz
from osv.orm import browse_record, browse_null
from osv import fields, osv, orm
from datetime import datetime, timedelta
from dateutil import *
from dateutil.tz import *

from tools.translate import _


import openstc



""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
""" Task """""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""

class task(OpenbaseCore):
    _name = "project.task"
    _description = "Task ctm"
    _inherit = "project.task"
    __logger = logging.getLogger(_name)




    #Overrides _is_template method of project module
    def _is_template(self, cr, uid, ids, field_name, arg, context=None):
        res = {}
        for task in self.browse(cr, uid, ids, context=context):
            res[task.id] = True
        return res




    #Calculates if agent belongs to 'arg' code group
    def _get_active(self, cr, uid, ids, fields, arg, context):
         res = {}
         user_obj = self.pool.get('res.users')
         task_obj = self.pool.get('project.task')
         team_obj = self.pool.get('openstc.team')
         project_obj = self.pool.get('project.project')

         user = user_obj.browse(cr, uid, uid,context)


         for id in ids:
            task = task_obj.browse(cr, uid, id, context=context)

            task_user_id = task_team_id = team_manager_id = task_project_id = project_service_id = False
            if isinstance(task.user_id, browse_null)!= True :
                task_user_id = task.user_id.id

            if isinstance(task.team_id, browse_null)!= True :
                task_team_id = task.team_id.id
                team = team_obj.browse(cr, uid, task.team_id.id, context=context)

            if task_team_id!= False :
                if isinstance(team.manager_id, browse_null)!= True :
                    team_manager_id = team.manager_id.id

            if isinstance(task.project_id, browse_null)!= True :
                task_project_id = task.project_id.id

            if task_project_id != False :
                project = project_obj.browse(cr, uid, task_project_id, context=context)
                try:
                   if isinstance(project.service_id, browse_null)!= True :
                       project_service_id = project.service_id.id
                except orm.except_orm, inst:
                     project_service_id = False

            belongsToOfficer = (task_user_id!=False and task_user_id == user.id) or (team_manager_id!=False and team_manager_id == task_user_id)
            belongsToTeam = task_team_id in ( t.id for t in user.team_ids )
            belongsToServiceManager = project_service_id in (s.id for s in user.service_ids) and user.isManager == True
            res[id] = True if belongsToOfficer or belongsToTeam or belongsToServiceManager or user.isDST else False
         return res

    def getUserTasksList(self, cr, uid, domain=[], fields=[], context=None):
        #in taskLists, absences are removed from result
        domain.extend([('state','!=','absent')])
        #first i get tasks with filter asked by UI
        res_ids = self.search(cr, uid, domain, context=context)
        res_filtered = [item[0] for item in self._get_active(cr, uid, res_ids, 'active', False, context=context).items() if item[1]]
        ret = self.read(cr, uid, res_filtered, fields, context=context)
        return ret

    #if tasks has an inter, returns service of this inter, else returns user services (returns empty list in unexpected cases)
    def get_services_authorized(self, cr, uid, id, context=None):
        ret = []
        if id:
            task = self.browse(cr, uid, id,context=context)
            if task.project_id:
                ret = [task.project_id.service_id and task.project_id.service_id.id] or []
            else:
                ret = self.pool.get("res.users").read(cr, uid, uid, ['service_ids'])['service_ids']
        else:
            ret = self.pool.get("res.users").read(cr, uid, uid, ['service_ids'])['service_ids']
        return ret

    def get_vehicules_authorized(self, cr, uid, id, context=None):
        service_id = self.get_services_authorized(cr, uid, id, context=context)
        ret = []
        if service_id:
            vehicule_ids = self.pool.get("openstc.equipment").search(cr, uid, ['&','|',('technical_vehicle','=',True),('commercial_vehicle','=',True),('service_ids','in',service_id)])
            ret = self.pool.get("openstc.equipment").read(cr, uid, vehicule_ids, ['id','name','type'],context=context)
        return ret

    def get_materials_authorized(self, cr, uid, id, context=None):
        service_id = self.get_services_authorized(cr, uid, id, context=context)
        ret = []
        if service_id:
            material_ids = self.pool.get("openstc.equipment").search(cr, uid, ['&','|',('small_material','=',True),('fat_material','=',True),('service_ids','in',service_id)])
            ret = self.pool.get("openstc.equipment").read(cr, uid, material_ids, ['id','name','type'],context=context)
        return ret

    #user can make survey of the task if it's an officer task, or a team task and user is a foreman / manager
    def _task_survey_rights(self, cr, uid, record, groups_code):
        ret = False
        if not record.team_id:
            ret = True
        else:
            ret = 'OFFI' not in groups_code
        return ret

    def _get_agent_or_team_name(self, cr, uid, ids, name, args,context=None):
        ret = {}.fromkeys(ids, '')
        for task in self.browse(cr, uid, ids, context=context):
            if task.user_id:
                ret[task.id] = task.user_id.name_get()[0][1]
            elif task.team_id:
                ret[task.id] = task.team_id.name_get()[0][1]
            elif task.partner_id:
                ret[task.id] = task.partner_id.name_get()[0][1]
        return ret

    def _get_task_from_inter(self, cr, uid, ids, context=None):
        return self.pool.get('project.task').search(cr, uid, [('project_id','in',ids)],context=context)

    def _get_hr_cost(self, cr, uid, task, task_work, presta_cost, context):
        """
        Get Human resource cost

        :param cr: database cursor
        :param uid: current user id
        :param task: current task
        :param task_work: current task work
        :param presta_cost: if external recipient cost indicated directly in the input

        """
        user_ids = []
        user_obj = self.pool.get('res.users')
        labour_cost = 0.0
        if task.user_id:
            # officer timesheet cost equal hourly rate multiplied by time spent
            labour_cost = task.user_id.cost * task_work.hours
        elif task.team_id:
             # team timesheet cost equal addition of hourly rate by officer multiplied by time spent
            for user_id in user_obj.browse(cr, uid, task.team_id.user_ids, context=context):
                labour_cost += user_id.id.cost * task_work.hours
        else:
             # external timesheet cost equal cost indicated directly in the input
            labour_cost = presta_cost
        return labour_cost

    def _get_equipment_cost(self, cr, uid, task, task_work, context):
        """
        Get operating cost takes into account equipments

        :param cr: database cursor
        :param uid: current user id
        :param task: current task
        :param task_work: current task work

        """
        equipment_obj = self.pool.get('openstc.equipment')
        equipment_cost = 0.0
        for equipment_id in task.equipment_ids:
            #equipments cost
            equipment_cost += equipment_id.hour_price * task_work.hours
        return equipment_cost

    def _get_consumable_cost(self, cr, uid, task, task_work, context):
        """
        Get operating cost takes into account consumables

        :param cr: database cursor
        :param uid: current user id
        :param task: current task
        :param task_work: current task work
        """
        consumable_obj = self.pool.get('openbase.consumable')
        consumable_cost = 0.0
        for consumable in task_work.consumables:
            #consumables cost
            consumable_cost += consumable.unit_price * consumable.quantity
        return consumable_cost

    def _get_task(self, cr, uid, ids, context=None):
        """
        Get task works

        :param cr: database cursor
        :param uid: current user id
        :param ids: task ids

        """
        result = {}
        for work in self.pool.get('project.task.work').browse(cr, uid, ids, context=context):
            if work.task_id: result[work.task_id.id] = True
        return result.keys()


    _fields_names = {'equipment_names':'equipment_ids', 'consumable_names':'consumable_ids'}

    _actions = {
        'print':lambda self,cr,uid,record, groups_code: record.state in ('draft','open'),
        'cancel':lambda self,cr,uid,record, groups_code: record.state == 'draft',
        'delete':lambda self,cr,uid,record, groups_code: record.state == 'draft',
        'replan': lambda self,cr,uid,record, groups_code: record.state == 'done',
        'normal_mode_finished': lambda self,cr,uid,record, groups_code: self._task_survey_rights(cr, uid, record, groups_code) and record.state == 'open',
        'normal_mode_unfinished': lambda self,cr,uid,record, groups_code: self._task_survey_rights(cr, uid, record, groups_code) and record.state == 'open',
        'light_mode_finished': lambda self,cr,uid,record, groups_code: self._task_survey_rights(cr, uid, record, groups_code) and record.state == 'draft',
        'light_mode_unfinished': lambda self,cr,uid,record, groups_code: self._task_survey_rights(cr, uid, record, groups_code) and record.state == 'draft',
        'modify': lambda self,cr,uid,record, groups_code: True,

        }



    _columns = {
        'active':fields.function(_get_active, method=True,type='boolean', store=False),
        'ask_id': fields.many2one('openstc.ask', 'Demande', ondelete='set null', select="1"),
        'project_id': fields.many2one('project.project', 'Intervention', ondelete='set null'),
        'equipment_ids':fields.many2many('openstc.equipment', 'openstc_equipment_task_rel', 'task_id', 'equipment_id', 'Equipments'),
        'consumable_ids':fields.many2many('openbase.consumable', 'openbase_consumable_task_rel', 'task_id', 'consumable_id', 'Fournitures'),
        'parent_id': fields.many2one('project.task', 'Parent Task'),
        'intervention_assignement_id':fields.many2one('openstc.intervention.assignement', 'Assignement'),
        'absent_type_id':fields.many2one('openstc.absent.type', 'Type d''abscence'),
        'category_id':fields.many2one('openstc.task.category', 'Category'),
        'state': fields.selection([('absent', 'Absent'),('draft', 'New'),('open', 'In Progress'),('pending', 'Pending'), ('done', 'Done'), ('cancelled', 'Cancelled')], 'State', readonly=True, required=True,
                                  help='If the task is created the state is \'Draft\'.\n If the task is started, the state becomes \'In Progress\'.\n If review is needed the task is in \'Pending\' state.\
                                  \n If the task is over, the states is set to \'Done\'.'),
        'team_id': fields.many2one('openstc.team', 'Team'),

        'km': fields.integer('Km', select=1),
        'oil_qtity': fields.float('oil quantity', select=1),
        'oil_price': fields.float('oil price', select=1),
        'site1':fields.related('project_id','site1',type='many2one',relation='openstc.site', string='Site',store={'project.task':[lambda self,cr,uid,ids,ctx={}:ids, ['project_id'], 10],
                                                                                                                  'project.project':[_get_task_from_inter, ['site1'],11]}),
        'inter_desc': fields.related('project_id', 'description', type='char'),
        'inter_equipment': fields.related('project_id', 'equipment_id', type='many2one',relation='openstc.equipment'),
        'cancel_reason': fields.text('Cancel reason'),
        'agent_or_team_name':fields.function(_get_agent_or_team_name, type='char', method=True, store=False),
        'cost':fields.float('Cost', type='float', digits=(5,2)),
        'hr_cost':fields.float('Cost', type='float', digits=(5,2)),
        'equipment_cost':fields.float('Cost', type='float', digits=(5,2)),
        'consumable_cost':fields.float('Cost', type='float', digits=(5,2)),
    }

    _defaults = {'active': lambda *a: True, 'user_id':None}


    """
        Creates an orphan task : not attached to intervention
    """
    def createOrphan(self, cr, uid, ids, params, context=None):

        task_obj = self.pool.get(self._name)

        self.updateEquipment(cr, uid, params, context)

        res = super(task, self).create(cr, uid, params, context)
        new_task = task_obj.browse(cr, uid, res, context)

        self.createWork(cr, uid, new_task, params, context)

        return res


    """
        Report working hours on task
    """
    def reportHours(self, cr, uid, ids, params, context=None):

        #report_hours
        #remaining_hours

        task_obj = self.pool.get(self._name)
        #Get current task
        task = task_obj.browse(cr, uid, ids[0], context)
        #do nothing if task no found or not report hours
        if task==None or task == False : return False
        if not openstc._get_param(params, 'report_hours') : return False
        project = None
        project_obj = self.pool.get('project.project')
        ask_obj = self.pool.get('openstc.ask')
        #Get intervention's task
        if task.project_id!=None and task.project_id!=False :
            if task.project_id.id > 0 :
                project = project_obj.browse(cr, uid, [task.project_id.id], context=context)[0]
                #update intervention state
                if (project.state != 'template'):
                    #update intervention state  : pending because remaining_hours>0
                    project_obj.write(cr, uid, project.id, {
                        'state': 'pending',
                    }, context=context)

        #Prepare equipment list
        if params.has_key('equipment_ids') and len(params['equipment_ids'])>0 :
            equipment_ids = params['equipment_ids']
            if not isinstance(equipment_ids[0], list) and not isinstance(equipment_ids[0], tuple):
                equipment_ids = [(6,0,equipment_ids)]
        else :
            equipment_ids = []

        #Prepare consumable list
        consumable_ids = []
        if params.has_key('consumables') and len(params['consumables'])>0 :
            for consumable in params['consumables']:
                if consumable['id'] not in consumable_ids :
                    consumable_ids.append(consumable['id'])

        #update mobile equipment kilometers
        self.updateEquipment(cr, uid, params, ids[0], context)


        #Records report time
        self.createWork(cr, uid, task, params, context)

        #TODO cost calculation
        task = self.browse(cr, uid, ids[0], context=context)
        cost=hr_cost=equipment_cost=consumable_cost = 0.0
        for task_work in task.work_ids:
            presta_cost = 0.0 if params.has_key('cost')== False or params['cost']== '' else float(params['cost'])
            hr_cost += self._get_hr_cost(cr, uid, task, task_work, presta_cost , context)
            equipment_cost +=   self._get_equipment_cost(cr, uid, task, task_work, context)
            consumable_cost +=  self._get_consumable_cost(cr, uid, task, task_work, context)
        cost = hr_cost + equipment_cost + consumable_cost

        self.__logger.warning('----------------- Write task %s ------------------------------', ids[0])
        #Update Task
        task_obj.write(cr, uid, ids[0], {
                'state': 'done',
                'date_start': task.date_start or openstc._get_param(params, 'date_start'),
                'date_end': task.date_end or openstc._get_param(params, 'date_end'),
                'team_id': task.team_id and task.team_id.id or openstc._get_param(params, 'team_id'),
                'user_id': task.user_id and task.user_id.id or openstc._get_param(params, 'user_id'),
                'partner_id': task.partner_id and task.partner_id.id or openstc._get_param(params, 'partner_id'),
                'cost': cost ,
                'hr_cost': hr_cost ,
                'equipment_cost': equipment_cost ,
                'consumable_cost': consumable_cost ,
                'equipment_ids': equipment_ids,
                'consumable_ids': [(6,0,consumable_ids)],
                'remaining_hours': 0,
                'km': 0 if params.has_key('km')== False else params['km'],
                'oil_qtity': 0 if params.has_key('oil_qtity')== False else params['oil_qtity'],
                'oil_price': 0 if params.has_key('oil_price')== False else params['oil_price'],
            }, context=context)

        if openstc._test_params(params,['remaining_hours'])!=False:
            #Not finnished task : Create new task for planification
            task_obj.create(cr, uid, {
                 'name'              : task.name,
                 'parent_id'         : task.id,
                 'project_id'        : task.project_id.id or False,
                 'state'             : 'draft',
                 'planned_hours'     : 0 if params.has_key('remaining_hours')== False else params['remaining_hours'],
                 'remaining_hours'   : 0 if params.has_key('remaining_hours')== False else params['remaining_hours'],
                 'user_id'           : None,
                 'team_id'           : None,
                 'partner_id'        : None,
                 'date_end'          : None,
                 'date_start'        : None,
             }, context)
        else:
            #Finnished task
            if project:
                project_obj.check_remaining_tasks_and_validate(cr, uid, project.id, context=context)

        return True

    """
        Update equipment information when task has done
    """
    def updateEquipment(self, cr, uid, params, task_id, context):
        equipment_obj = self.pool.get('openstc.equipment')
        equipment_lines_obj = self.pool.get('openstc.equipment.lines')
        #Update kilometers on vehucule
        if openstc._test_params(params,['vehicule','km'])!= False :
            equipment_obj.write(cr, uid, params['vehicule'], {
                    'km': 0 if params.has_key('km')== False else params['km'],
                 }, context=context)

            equipment_lines_obj.create(cr, uid, {
                    'km': 0 if params.has_key('km')== False else params['km'],
                    'oil_qtity': 0 if params.has_key('oil_qtity')== False else params['oil_qtity'],
                    'oil_price': 0 if params.has_key('oil_price')== False else params['oil_price'],
                    'equipment_id': params['vehicule'],
                    'task_id': task_id
                }, context=context)




    """
        Report working time for task
    """
    def createWork(self, cr, uid, task, params, context):
        task_obj = self.pool.get('project.task')
        task_work_obj = self.pool.get('project.task.work')
        #update task work
        work_id = task_work_obj.create(cr, uid, {
             'name': task.name,
             #TODO : manque l'heure
             'date':  datetime.now().strftime('%Y-%m-%d') if params.has_key('date')== False  else params['date'],
             'task_id': task.id,
             'hours':  openstc._get_param(params, 'report_hours'),
             'user_id': task.user_id.id or False,
             'team_id': task.team_id.id or False,
             'partner_id': task.partner_id.id or False,
             'company_id': task.company_id.id or False,
            }, context=context)

        work_consumables_obj = self.pool.get('openstc.task.work.consumables')
        if params.has_key('consumables'):
            consumables = params['consumables']
            for consumable in consumables:
                  work_consumable_id = work_consumables_obj.create(cr, uid, {
                     'dqe': '' if consumable['dqe']== False else consumable['dqe'],
                     'quantity':  0 if consumable['quantity']== False else consumable['quantity'],
                     'unit_price': 0 if consumable['unit_price']== False else consumable['unit_price'],
                     'work_id': work_id,
                     'consumable_id': consumable['id']
                    }, context=context)





    def create(self, cr, uid, vals, context=None):
        res = super(task, self).create(cr, uid, vals, context=context)
        #if task is created with reports_hours, update task_work and task values
        self.reportHours(cr, uid, [res], vals, context=context)
        return res

    def write(self, cr, uid, ids, vals, context=None):
        #if we want to cancel task, we update some values automatically
        if 'state' in vals and vals['state'] == 'cancelled':
            for mTask in self.browse(cr, uid, ids, context=context):
                if mTask.state <> 'cancelled':
                    values = {}
                    values.update({'cancel_reason': openstc._get_param(vals, 'cancel_reason') })
                    values.update({'remaining_hours': 0.0})
                    vals.update(values)
                    if not mTask.date_end:
                        vals.update({ 'date_end':time.strftime('%Y-%m-%d %H:%M:%S')})
                    super(task,self).write(cr, uid, [mTask.id],vals, context=context)
                    self.pool.get("project.project").action_finished(cr, uid, [mTask.project_id.id])
        else:
            res = super(task, self).write(cr, uid, ids, vals, context=context)
            #if task(s) have hours to report, we update task works and those tasks
            if not isinstance(ids, list):
                ids = [ids]
            self.reportHours(cr, uid, ids, vals, context=context)

        return True
    
    def unlink(self, cr, uid, ids, context=None):
        ids = ids if isinstance(ids, list) else [ids]
        inter_obj = self.pool.get('project.project')
        inter_ids = inter_obj.search(cr, uid, [('tasks.id', 'in', ids)], context=context)
        
        ret = super(task, self).unlink(cr, uid, ids, context=context)
        inter_obj.check_remaining_tasks_and_validate(cr, uid, inter_ids, context=context)
        return ret

    def cancel(self, cr, uid, ids, params, context={}):
        """
        Cancel Task
        """
        if not isinstance(ids,list): ids = [ids]
        for task in self.browse(cr, uid, ids, context=context):
            if task.state <> 'cancelled':
                vals = {}

                vals.update({'state': 'cancelled'})
                vals.update({'cancel_reason': openstc._get_param(params, 'cancel_reason') })
                vals.update({'remaining_hours': 0.0})
                if not task.date_end:
                    vals.update({ 'date_end':time.strftime('%Y-%m-%d %H:%M:%S')})
                self.write(cr, uid, [task.id],vals, context=context)
            #message = _("The task '%s' is done") % (task.name,)
            #self.log(cr, uid, task.id, message)
        return True

    def planTasks(self, cr, uid, ids, params, context=None):

        """
        Plan tasks after drag&drop task on planning

        :param cr: database cursor
        :param uid: current user id
        :param ids: list of ids
        :param params: contains
            start_working_time : date/heure début de journée travaillée
            end_working_time : date/heure fin de journée
            start_lunch_time : date/heure début pause déjeuner
            end_lunch_time : date/heure fin pause déjeuner
            start_dt: date/heure du début de la plage souhaitée
            type : string key : 'officer', 'team', 'partner'
            calendar_id : celui de l'agent / ou celui de l'équipe, selon le type

        This method is used when plan tasks from client

        """

        self.log(cr, uid, ids[0], "planTasks")
        if not len(ids) == 1: raise Exception('Pas de tâche à planifier')

        #ret
        results = {}
        #date format
        timeDtFrmt = "%Y-%m-%d %H:%M:%S"

        #Get current task
        currentTask = self.browse(cr, uid, ids[0], context=context)
        #if task belongs to an intervention
        if currentTask.project_id:
            #Copy is true when intervention is a template
            copy = self.pool.get('project.project').is_template(cr, uid, [currentTask.project_id.id], context=context)


        if 'cpt' not in params:
            params['cpt'] = -1
            params["returnIds"] = [ids[0]]
        if 'number' not in params: params['number'] = 0
        #Init time to plan
        if 'timeToPlan' not in params: params['timeToPlan'] = currentTask.planned_hours
        #Planning is complete : return current task upgraded
        elif params['timeToPlan']==0 or not params['start_dt']:
            return  params["returnIds"]; #params['results']

        type = params['type']
        calendar_id = params['calendar_id']

        #Get all events on 'start_dt' for officer or team 'calendar_id'
        if 'events' not in params :
#            try:
            events = self.getTodayEventsById(cr, uid, ids, params, timeDtFrmt, context)
#            except Exception, e:
#                return e
        else:
            events = params['events']

        cpt = params['cpt']
        start_dt = params['start_dt']
        size = len(events)

        while True:
           cpt+=1
           #Get end date
           endDt = start_dt + timedelta(hours=params['timeToPlan'])
           if cpt<size:
               e = events[cpt]
               if(start_dt >= e['date_start'] and start_dt<=e['date_end']):
                    start_dt = e['date_end']
               elif start_dt > e['date_start']:
                    continue
               else:
                   break
           else:
               break


        if cpt  == size:
             #Task was not completely scheduled
            results.update({
                  'name':  currentTask.name,
                  'project_id': currentTask.project_id.id,
                  'parent_id': currentTask.id if copy else False,
                  'state': 'draft',
                  'planned_hours': params['timeToPlan'],
                  'remaining_hours': params['timeToPlan'],
                  'user_id': None,
                  'team_id': None,
                  'partner_id': None,
                  'date_end': None,
                  'date_start': None,
            })
            #Return to plan with the remaining time
            self.write(cr, uid, [currentTask.id],results, context=context)
            params['timeToPlan'] = 0
            params['results'] = results
        else:
            #Get next date
            nextDt = events[cpt]['date_start']
            #hours differences to next date
            diff = (nextDt-start_dt).total_seconds()/3600

            if (params['timeToPlan'] - diff) == 0 :
                #whole task is completely schedulable (all hours) before next so timeToPlan is set to 0
                params['timeToPlan'] = 0
                endDt = nextDt
            elif (params['timeToPlan'] - diff) > 0 :
                #task is not completely schedulable
                params['timeToPlan'] = params['timeToPlan'] - diff
                endDt = nextDt
            else:
                #there is less time to plan the number of hours possible before the next date, diff is re-calculate
                params['timeToPlan'] = 0
                diff = (endDt-start_dt).total_seconds()/3600


            if params['number'] > 0 :
                #The task is divided : title is changed"
                title = "(Suite-" + str(params['number']) + ")" + currentTask.name
            else:
                title = currentTask.name

            results = {
                'name': title,
                'planned_hours': diff,
                'remaining_hours': diff,
                'team_id': calendar_id if type == 'team' else None,
                'user_id': calendar_id if type == 'officer' else None,
                'partner_id': calendar_id if type == 'partner' else None,
                'date_start': datetime.strftime(start_dt,timeDtFrmt),
                'date_end': datetime.strftime(endDt,timeDtFrmt),
                'state': 'open',
                'parent_id': currentTask.id if copy else False,
                'project_id': currentTask.project_id.id,
            }

            #All time is scheduled and intervention is not a template
            if params['timeToPlan'] == 0 and not copy:
                #Update task
               self.write(cr, uid, [currentTask.id],results, context=context)

            else:
                #Create task
                id = self.create(cr, uid, results);
                params["returnIds"].append(id)

        params['results'] = results
        params['start_dt'] = endDt
        params['number'] += 1
        params['cpt'] = cpt - 1
        #re-call the method with new params
        return self.planTasks(cr, uid, ids, params, context)

    def getTodayEventsById(self, cr, uid, ids, params, timeDtFrmt, context=None):
        """
        Plan tasks after drag&drop task on planning

        :param cr: database cursor
        :param uid: current user id
        :param ids: list of ids
        :param params: contains
            start_working_time : date/heure début de journée travaillée
            end_working_time : date/heure fin de journée
            start_lunch_time : date/heure début pause déjeuner
            end_lunch_time : date/heure fin pause déjeuner
            start_dt: date/heure du début de la plage souhaitée
            type : string key : 'officer', 'team', 'partner'
            calendar_id : celui de l'agent / ou celui de l'équipe, selon le type

        This method is used to get events on start_dt (lunch including) for officer or team (calendar_id)

        """
        if not set(('start_working_time','end_working_time','start_lunch_time','end_lunch_time','start_dt','calendar_id')).issubset(params) :
            raise Exception('Erreur : il manque des paramètres pour pouvoir planifier (Heure d''embauche, heure de déjeuner...) \n Veuillez contacter votre administrateur ')

        #Date format passed by javascript client : date from utc.
        #Client swif lose the timezone because of the serialisation in JSON request (JSON.stringify)
        timeDtFrmtWithTmz = "%Y-%m-%dT%H:%M:%S.000Z"
        #Get user context
        context_tz = self.pool.get('res.users').read(cr,uid,[uid], ['context_tz'])[0]['context_tz'] or 'Europe/Paris'
        tzinfo = pytz.timezone(context_tz)

        events= []

        todayDt = datetime.now(tzinfo)
        #Calculate time differencee between utc and user's timezone
        deltaTz = int((datetime.utcoffset(todayDt).total_seconds())/3600)

        #Get Start and end working time, lunch start and stop times
        start_dt = datetime.strptime(params['start_dt'],timeDtFrmtWithTmz)
        start_working_time = start_dt.replace(hour= (int(params['start_working_time'])-deltaTz),minute=0, second=0, microsecond=0)
        start_lunch_time = start_dt.replace( hour = (int(params['start_lunch_time'])-deltaTz),minute=0, second=0, microsecond=0 )
        end_lunch_time = start_dt.replace( hour = (int(params['end_lunch_time'])-deltaTz),minute=0, second=0, microsecond=0 )

        #Add in list
        events.append({'title': "lunchTime", 'date_start': start_lunch_time,
                       'date_end': end_lunch_time})
        end_working_time = start_dt.replace( hour = (int(params['end_working_time'])-deltaTz),minute=0, second=0, microsecond=0 )
        events.append({'title': "end_working_time", 'date_start': end_working_time,
                       'date_end': end_working_time})

        task_ids = []
        if params['type'] == 'team':
            #Get all tasks on 'start_dt' for team
            task_ids = self.search(cr,uid,
                ['&',('date_start','>=', datetime.strftime(start_working_time,timeDtFrmt)),
                    ('date_start','<=', datetime.strftime(end_working_time,timeDtFrmt)),
                '|',('team_id','=',params['calendar_id']),
                    ('user_id','in', self.pool.get('openstc.team').read(cr, uid, params['calendar_id'], ['user_ids'])['user_ids'] )
                ])
        elif params['type'] == 'officer':
            #Get all tasks on 'start_dt' for officer
            task_ids = self.search(cr,uid,
                ['&',('date_start','>=', datetime.strftime(start_working_time,timeDtFrmt)),
                    ('date_start','<=', datetime.strftime(end_working_time,timeDtFrmt)),
                 '|',('user_id','=', params['calendar_id']),
                    ('team_id','in', self.pool.get('res.users').read(cr, uid, params['calendar_id'], ['team_ids'])['team_ids'] )
                ])
        else:
            #Get all tasks on 'start_dt' for officer
            task_ids = self.search(cr,uid,
                ['&',('date_start','>=', datetime.strftime(start_working_time,timeDtFrmt)),
                    ('date_start','<=', datetime.strftime(end_working_time,timeDtFrmt)),
                    ('partner_id','=', params['calendar_id'])
                ])

        tasks = self.read(cr,uid,task_ids, ['name','date_start','date_end'])
        #Add tasks in list
        for task in tasks :
            events.append({'title': task['name'], 'date_start': datetime.strptime(task['date_start'],timeDtFrmt),
                           'date_end': datetime.strptime(task['date_end'],timeDtFrmt) })

        #Sort task
        events.sort(key=operator.itemgetter('date_start'))
        params['events'] = events
        params['start_dt'] = start_dt
        #Return tasks
        return events

task()

class project_work(osv.osv):
    _name = "project.task.work"
    _description = "Project Task Work"
    _inherit = "project.task.work"


    _columns = {
        'consumables': fields.one2many('openstc.task.work.consumables', 'work_id', 'Consumable lines'),
    }

project_work()

""" work line for consumable record list
"""
class project_work_consumables(osv.osv):
    _name = "openstc.task.work.consumables"
    _description = "Project Task Work consumables"

    _columns = {
        'dqe': fields.char('Detailed Quantitative Quantities', size=128),
        'quantity': fields.float('Quantity', digits=(4,2)),
        'unit_price':fields.float('Unit Price', digits=(4,2)),
        'work_id':fields.many2one('project.task.work', 'Task work'),
        'consumable_id':fields.many2one('openbase.consumable', 'Consumable'),
    }

project_work()

""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
""" Task categories """""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""

class openstc_task_category(OpenbaseCore):

    def name_get(self, cr, uid, ids, context=None):
        if not len(ids):
            return []
        reads = self.read(cr, uid, ids, ['name','parent_id'], context=context)
        res = []
        for record in reads:
            name = record['name']
            if record['parent_id']:
                name = record['parent_id'][1]+' / '+name
            res.append((record['id'], name))
        return res

    def _name_get_fnc(self, cr, uid, ids, prop, unknow_none, context=None):
        res = self.name_get(cr, uid, ids, context=context)
        return dict(res)


    _actions = {
        'delete':lambda self,cr,uid,record, groups_code: 'DIRE' in groups_code,
        'update': lambda self,cr,uid,record, groups_code: 'MANA' in groups_code or 'DIRE' in groups_code,
        'create': lambda self,cr,uid,record,groups_code: 'MANA' in groups_code or 'DIRE' in groups_code,

    }

    _fields_names = {'service_names':'service_ids'}

    _name = "openstc.task.category"
    _description = "Task Category"
    _columns = {
        'name': fields.char('Name', size=64, required=True, select=True),
        'code': fields.char('Code', size=32),
        'complete_name': fields.function(_name_get_fnc, type="char", string='Name', method=True, store={'openstc.task.category':[lambda self,cr,uid,ids,ctx={}:ids, ['name','parent_id'],10]}),
        'parent_id': fields.many2one('openstc.task.category','Parent Category', select=True, ondelete='cascade'),
        'child_id': fields.one2many('openstc.task.category', 'parent_id', string='Child Categories'),
        'sequence': fields.integer('Sequence', select=True, help="Gives the sequence order when displaying a list of product categories."),
        'parent_left': fields.integer('Left Parent', select=1),
        'parent_right': fields.integer('Right Parent', select=1),
        'service_ids':fields.many2many('openstc.service', 'openstc_task_category_services_rel', 'task_category_id', 'service_id', 'Services'),
        'unit': fields.char('Unit', size=32),
        'quantity': fields.integer('Quantity'),
        'tasksAssigned': fields.one2many('project.task', 'category_id', "tasks"),

    }

    _sql_constraints = [
        ('category_uniq', 'unique(name,parent_id)', '*name* / Name and Category parent must be unique! Change name or category parent'),
        ('code_uniq', 'unique (code)', '*code* /codeNameUniq!')
    ]


    _parent_name = "parent_id"
    _parent_store = True
    _parent_order = 'sequence, name'
    _order = 'parent_left'

    def _check_recursion(self, cr, uid, ids, context=None):
        level = 100
        while len(ids):
            cr.execute('select distinct parent_id from openstc_task_category where id IN %s',(tuple(ids),))
            ids = filter(None, map(lambda x:x[0], cr.fetchall()))
            if not level:
                return False
            level -= 1
        return True

    _constraints = [
        (_check_recursion, 'Error ! You cannot create recursive categories.', ['parent_id'])
    ]
    def child_get(self, cr, uid, ids):
        return [ids]

openstc_task_category()


""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
""" Project task type """""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""

class project_task_type(OpenbaseCore):
    _name = "project.task.type"
    _description = "project.task.type"
    _inherit = "project.task.type"

    _columns = {

    }

project_task_type()


""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
""" Abstent task history """""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""

class project_task_history(OpenbaseCore):
    _name = 'project.task.history'
    _description = 'History of Tasks'
    _inherit = "project.task.history"

    _columns = {
        'state': fields.selection([('finished', 'Finished'),('absent', 'Absent'),('draft', 'New'),('open', 'In Progress'),('pending', 'Pending'), ('done', 'Done'), ('cancelled', 'Cancelled')], 'State'),

    }

class equipment_lines(osv.osv):
    _inherit = "openstc.equipment.lines"
    _columns = {
         'task_id':fields.many2one('project.task', 'Task'),
        }
    
equipment_lines()
