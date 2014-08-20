# -*- coding: utf-8 -*-

##############################################################################
#    Copyright (C) 2012 SICLIC http://siclic.fr
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>
#
#############################################################################


from openbase.openbase_core import OpenbaseCore


import netsvc
import pytz
from osv.orm import browse_record, browse_null
from osv import fields, osv, orm
from datetime import datetime, timedelta
from dateutil import *
from dateutil.tz import *

from tools.translate import _

import openstc

""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
""" Interventions """""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""


class project(OpenbaseCore):
    _name = "project.project"
    _description = "Interventon stc"
    _inherit = "project.project"


    """
        Mail templates
    """
    def _mail_templates(self, cr, uid, context=None):
        return  {'scheduled':'openstc_email_template_project_scheduled'}

    def _complete_name(self, cr, uid, ids, name, args, context=None):
        return super(project, self)._complete_name(cr, uid, ids, name, args, context=context)

    def _get_projects_from_tasks(self, cr, uid, task_ids, context=None):
#        tasks = self.pool.get('project.task').browse(cr, uid, task_ids, context=context)
#        project_ids = [task.project_id.id for task in tasks if task.project_id]
        project_ids = self.pool.get('project.project').search(cr, uid, [('tasks','in', task_ids)], context=context)
        return self.pool.get('project.project')._get_project_and_parents(cr, uid, project_ids, context)

    def _get_project_and_parents(self, cr, uid, ids, context=None):
        """ return the project ids and all their parent projects """
        res = set(ids)
        while ids:
            cr.execute("""
                SELECT DISTINCT parent.id
                FROM project_project project, project_project parent, account_analytic_account account
                WHERE project.analytic_account_id = account.id
                AND parent.analytic_account_id = account.parent_id
                AND project.id IN %s
                """, (tuple(ids),))
            ids = [t[0] for t in cr.fetchall()]
            res.update(ids)
        return list(res)

    #Overrides project : progress_rate ratio on planned_hours instead of 'total_hours'
    def _progress_rate(self, cr, uid, ids, names, arg, context=None):
        child_parent = self._get_project_and_children(cr, uid, ids, context)
        # compute planned_hours, total_hours, effective_hours specific to each project
        cr.execute("""
            SELECT project_id, COALESCE(SUM(planned_hours), 0.0),
                COALESCE(SUM(total_hours), 0.0), COALESCE(SUM(effective_hours), 0.0)
            FROM project_task WHERE project_id IN %s AND state <> 'cancelled'
            GROUP BY project_id
            """, (tuple(child_parent.keys()),))
        # aggregate results into res
        res = dict([(id, {'planned_hours':0.0,'total_hours':0.0,'effective_hours':0.0}) for id in ids])
        for id, planned, total, effective in cr.fetchall():
            # add the values specific to id to all parent projects of id in the result
            while id:
                if id in ids:
                    res[id]['planned_hours'] += planned
                    res[id]['total_hours'] += total
                    res[id]['effective_hours'] += effective
                id = child_parent[id]
        # compute progress rates
        for id in ids:
            if res[id]['planned_hours']:
                res[id]['progress_rate'] = round(100.0 * res[id]['effective_hours'] / res[id]['planned_hours'], 2)
            else:
                res[id]['progress_rate'] = 0.0
        return res

    """
    build tooltip information
    """
    def _tooltip(self, cr, uid, ids, myFields, arg, context):
        res = {}

        project_obj = self.pool.get('project.project')
        task_obj = self.pool.get('project.task')

        for inter in self.browse(cr, uid, ids, context=context):
            id = inter.id
            res[id] = ''
            if inter :
                first_date = None
                last_date = None
                allPlanned = True
                for task in inter.tasks :
                    first_date = max(first_date,task.date_start)

                    last_date = max(last_date, task.date_end)

                    if task.state == 'draft' :
                        allPlanned = False

                if last_date :
                     last_date = fields.datetime.context_timestamp(cr, uid,
                            datetime.strptime(last_date, '%Y-%m-%d  %H:%M:%S')
                            , context)

                if first_date :
                     first_date = fields.datetime.context_timestamp(cr, uid,
                            datetime.strptime(first_date, '%Y-%m-%d  %H:%M:%S')
                            , context)


                if first_date :
                    if inter.progress_rate >= 100 :
                        res[id] = _(' Ended date ') + last_date.strftime(_("%A, %d %B %Y %H:%M").encode('utf-8')).decode('utf-8')
                    elif inter.progress_rate == 0 :
                        res[id] = _(' Scheduled start date ') + first_date.strftime(_("%A, %d %B %Y %H:%M").encode('utf-8')).decode('utf-8')

                    elif last_date and allPlanned:
                        res[id] = _(' Scheduled end date ') + last_date.strftime(_("%A, %d %B %Y %H:%M").encode('utf-8')).decode('utf-8')
                    else :
                        res[id] = _(' All tasks not planned ')

                if inter.state == 'cancelled' :
                    if inter.cancel_reason:
                      res[id] += inter.cancel_reason
                    else:
                      res[id] = _(' intervention cancelled ')

        return res


    def _overPourcent(self, cr, uid, ids, myFields, arg, context):
        res = {}

        project_obj = self.pool.get('project.project')
        task_obj = self.pool.get('project.task')

        for id in ids:
            res[id] = 0
            inter = self.browse(cr, uid, id, context)
            if inter :
                if inter.planned_hours :
                    res[id] = round(100.0 * inter.effective_hours / inter.planned_hours, 0);
        return res

    #if inter exists and is associated to a service, returns this service_id, else returns user services
    def get_services_authorized(self, cr, uid, id, context=None):
        if id:
            inter = self.browse(cr, uid, id, context=context)
            if inter.service_id:
                return [inter.service_id.id]

        return self.pool.get("res.users").read(cr, uid, uid, ['service_ids'])['service_ids']


    def get_task_categ_authorized(self, cr, uid, id, context=None):
        service_ids = self.get_services_authorized(cr, uid, id, context=context)
        ret = []
        if service_ids:
            task_ids = self.pool.get("openstc.task.category").search(cr, uid, [('service_ids','in',service_ids)])
            ret = self.pool.get("openstc.task.category").read(cr, uid, task_ids, ['id','name'])
        return ret

    _actions = {
        'cancel':lambda self,cr,uid,record,groups_code: record.state in ('open','scheduled'),
        'plan_unplan':lambda self,cr,uid,record,groups_code: (record.state == 'open' and not self.pool.get("project.task").search(cr, uid,[('state','=','draft'),('project_id','=',record.id)])) or record.state == 'scheduled' ,
        'add_task':lambda self,cr,uid,record,groups_code: record.state in ('open','template'),
        'print': lambda self,cr,uid,record,groups_code: True,
        'modify': lambda self,cr,uid,record,groups_code: True,
        'create': lambda self,cr,uid,record,groups_code: True,

        }


    def _searchOverPourcent(self, cr, uid, obj, name, args, context=None):
        if args and len(args[0]) >= 2:
            arg = args[0]
            where = ''
            if arg[2] is False:
                where = 'planned_hours = 0 or effective_hours / planned_hours = 0'
            else:
                where = 'planned_hours > 0 and 100 * effective_hours / planned_hours %s %s' % (arg[1], arg[2])
            cr.execute('select id from %s where %s' % (self._table, where))
            ret = cr.fetchall()
            return [('id','in',[item[0] for item in ret])]
        return [('id','>',0)]

    def _get_cost(self, cr, uid, ids, name, args, context):
        """
        Set project cost when one task associated is udpated

        :param cr: database cursor
        :param uid: current user id
        :param name: name field (cost)
        :param args: other agrs

        """

        ret = dict([(id, {'cost':0.0,'hr_cost':0.0,'equipment_cost':0.0,'consumable_cost':0.0}) for id in ids])
        task_obj = self.pool.get('project.task')

        for project in self.browse(cr, uid, ids, context=context):
            for task in project.tasks:
                ret[project.id]['cost'] += task.cost
                ret[project.id]['hr_cost'] += task.hr_cost
                ret[project.id]['equipment_cost'] += task.equipment_cost
                ret[project.id]['consumable_cost'] += task.consumable_cost


        return ret

    def _get_task(self, cr, uid, ids, context=None):
        """
        Get tasks

        :param cr: database cursor
        :param uid: current user id
        :param ids: project ids

        """
        result = {}
        for task in self.pool.get('project.task').browse(cr, uid, ids, context=context):
            if task.project_id: result[task.project_id.id] = True
        return result.keys()

    _columns = {
        'complete_name': fields.function(_complete_name, string="Project Name", type='char', size=250, store=True),
        'ask_id': fields.many2one('openstc.ask', 'Demande', ondelete='set null', select="1", readonly=True),
        'create_uid': fields.many2one('res.users', 'Created by', readonly=True),
        'create_date' : fields.datetime('Create Date', readonly=True, select=True),
        'intervention_assignement_id':fields.many2one('openstc.intervention.assignement', 'Affectation'),
        'date_deadline': fields.date('Deadline',select=True),
        'site1': fields.many2one('openstc.site', 'Site principal', select=True),
        'state': fields.selection([('finished', 'Finished'),('template', 'Template'),('open', 'Open'),('scheduled', 'Scheduled'),('pending', 'Pending'), ('cancelled', 'Cancelled')],
                                  'State', readonly=True, required=True, help=''),

        'service_id': fields.many2one('openstc.service', 'Service', select=True),
        'description': fields.text('Description', select=True),
        'site_details': fields.text('Précision sur le site'),
        'cancel_reason': fields.text('Cancel reason'),


        'progress_rate': fields.function(_progress_rate, multi="progress", string='Progress', type='float', group_operator="avg", help="Percent of tasks closed according to the total of tasks todo.",
            store = {
                'project.project': (_get_project_and_parents, ['tasks', 'parent_id', 'child_ids'], 9),
                'project.task': (_get_projects_from_tasks, ['planned_hours', 'remaining_hours', 'work_ids', 'state'], 19),
            }),

        'tooltip' : fields.function(_tooltip, method=True, string='Tooltip',type='char', store=False),
        'overPourcent' : fields.function(_overPourcent, fnct_search=_searchOverPourcent, method=True, string='OverPourcent',type='float', store=False),
        'equipment_id': fields.many2one('openstc.equipment','Equipment', select=True),
        'has_equipment': fields.boolean('Request is about equipment'),
        'cost' : fields.function(_get_cost,  string='cost',type='float', multi="cost",
            store = {
                'project.project': (_get_project_and_parents, ['tasks'], 10),
                'project.task': (_get_task, ['cost'], 20),
            }),
        'hr_cost' : fields.function(_get_cost,  string='cost',type='float', multi="cost",
            store = {
                'project.project': (_get_project_and_parents, ['tasks'], 10),
                'project.task': (_get_task, ['cost'], 20),
            }),
        'equipment_cost' : fields.function(_get_cost,  string='cost',type='float', multi="cost",
            store = {
                'project.project': (_get_project_and_parents, ['tasks'], 10),
                'project.task': (_get_task, ['cost'], 20),
            }),
        'consumable_cost' : fields.function(_get_cost,  string='cost',type='float', multi="cost",
            store = {
                'project.project': (_get_project_and_parents, ['tasks'], 10),
                'project.task': (_get_task, ['cost'], 20),
            }),
    }

    #Overrides  set_template method of project module
    def set_template(self, cr, uid, ids, context=None):
        return True;

    def is_template(self, cr, uid, ids, context=None):
        if not(len(ids) == 1) : return false
        inter = self.pool.get('project.project').browse(cr, uid, ids[0], context=context)
        if isinstance(inter, browse_null)!= True :
            return inter.state == 'template' or False

    def _get_active_inter(self, cr, uid, context=None):
        if context is None:
            return False
        else:
            return context.get('active_id', False)

    def _get_ask(self, cr, uid, context=None):
        inter_id = self._get_active_inter(cr, uid, context)
        if inter_id :
            ask_id = self.pool.get('project.project').read(cr, uid, inter_id,['ask_id'],context)['ask_id']
            if ask_id :
                ask_id[0]
        return False

    def write(self, cr, uid, ids, vals, context=None):
        if not isinstance(ids, list):
            ids = [ids]
        res = super(project, self).write(cr, uid, ids, vals, context=context)
        task_obj = self.pool.get('project.task')
        ask_obj = self.pool.get('openstc.ask')
        #if we want to cancel inter, we cancel all tasks associated and close the parent ask
        if 'state' in vals and vals['state'] == 'cancelled':
            task_ids = task_obj.search(cr, uid, [('project_id.id','in',ids)],context=context)
            if task_ids:
                task_obj.write(cr, uid, task_ids, {'state':'cancelled',
                                                               'user_id':False,
                                                               'partner_id':False,
                                                               'team_id':False,
                                                               'date_end':False,
                                                               'date_start':False,
                                                               'cancel_reason':vals.get('cancel_reason',False)},context=context)
            ask_ids = [item['ask_id'][0] for item in self.read(cr, uid, ids, ['ask_id'],context=context) if item['ask_id']]
            if ask_ids:
                ask_obj.write(cr, uid, ask_ids, {'state':'finished'})
        if vals.has_key('state') :
            netsvc.LocalService('workflow').trg_validate(uid, self._name, ids[0], vals['state'], cr)
        return res



    """ Workflow actions"""""""""""""""""""""""""""""""""""""""""""""""""""""""
    """""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
    def action_open(self, cr, uid, ids):
        return True

    def action_template(self, cr, uid, ids):
        return True

    def action_scheduled(self, cr, uid, ids):
        self.valid_and_send_mail(cr, uid, ids,{'state':'scheduled'})
        return True

    def action_pending(self, cr, uid, ids):
        return True

    def action_cancelled(self, cr, uid, ids):
        return True

    """
    Close project if necessary
    @param vals: project id
    """
    def action_finished(self, cr, uid, ids):
        if self.is_to_closed( cr, uid, ids):
            self.write(cr, uid, ids, {'state':'finished'})
            ask_ids = [item['ask_id'][0] for item in self.read(cr, uid, ids, ['ask_id'],None) if item['ask_id']]
            if ask_ids:
                self.pool.get("openstc.ask").write(cr, uid, ask_ids, {'state':'finished'})

        return True

    """
    Test if all tasks are closed
    @param vals: project id
    @return: return True all tasks are closed
    """
    def is_to_closed(self,cr, uid, ids):
        inter = self.browse(cr, uid, ids[0], None)
        for task in inter.tasks:
            if task.state not in ('absent','done','cancelled'):
                return False
        return True

    """
    Test if send mail after action on ask
    @param vals: contains state
    @return: return True if current ask meets conditions to send email
    """
    def valid_and_send_mail(self, cr, uid, ids, vals, context=None):
        inter = self.browse(cr, uid, ids[0], context=context)
        send_mail = False
        if inter.ask_id.people_email != '':
            send_mail=True
        elif inter.ask_id.partner_id and inter.ask_id.partner_id.type_id :
            if inter.ask_id.partner_id.type_id.sending_mail :
                send_mail=True
        if not send_mail: return False

        try:
             self.send_mail(cr, uid, inter.id, vals, 'openstc', self._name,
                                self._mail_templates(cr, uid, context))
        #Except if type is not defined on partner, or ask has no partner (normaly not possible)
        except Exception,e:
            return False
        return True


    #Cancel intervention from swif
    def cancel(self, cr, uid, ids, params, context=None):
        #print("test"+params)
        project_obj = self.pool.get(self._name)
        project = project_obj.browse(cr, uid, ids[0], context)
        task_obj = self.pool.get('project.task')
        ask_obj = self.pool.get('openstc.ask')

        #update intervention's tasks
        if openstc._test_params(params, ['state','cancel_reason'])!= False:
            for task in project.tasks:
                 task_obj.write(cr, uid, [task.id], {
                    'state' : params['state'],
                    'user_id': None,
                    'team_id': None,
                    'partner_id': None,
                    'date_end': None,
                    'date_start': None,
                }, context=context)

            #update intervention with cancel's reason
            project_obj.write(cr, uid, ids[0], {
                    'state' : params['state'],
                    'cancel_reason': params['cancel_reason'],
                }, context=context)

            ask_id = project.ask_id.id
            #update ask state of intervention
            if ask_id :
                ask_obj.write(cr, uid, ask_id , {
                            'state': 'finished',
                        }, context=context)
        return True;
    
        ## Check if there is no more task to treat, finish the inter, else, do nothing
    def check_remaining_tasks_and_validate(self, cr, uid, ids, context=None):
        ids = ids if isinstance(ids, list) else [ids]
        #look for pending intervetions
        pending_inter_ids = self.search(cr, uid, [('id', 'in', ids), '|',('tasks.state', 'in', ['open','pending', 'draft']), ('tasks', '=', False)], context=context)
        #the intervention to close are the ones not present in pending_inter_ids
        toclose_inter_ids = [x for x in ids if x not in pending_inter_ids]
        if toclose_inter_ids:
            self.write(cr, uid, toclose_inter_ids, {'state': 'finished',}, context=context)
            
            ask_obj = self.pool.get('openstc.ask')
            toclose_ask_ids = ask_obj.search(cr, uid, [('intervention_ids.id', 'in', toclose_inter_ids)], context=context)
            if toclose_ask_ids:
                ask_obj.write(cr, uid, toclose_ask_ids, {'state':'finished'}, context=context)
        #TODO
        #send email ==>  email_text: demande 'finished',
        return toclose_inter_ids

    _defaults = {
        'ask_id' : _get_ask,
        'has_equipment': False,
    }

    _sql_constraints = [
        ('ask_uniq', 'unique(name,ask_id)', 'Demande déjà validée!'),
    ]


project()
